/**
 * pi-deck — reports this pi session's status to the pi-deck Stream Deck daemon.
 *
 * Each pi session writes one small JSON file to ~/.pi-deck/status/<id>.json,
 * tagged with the cmux workspace and surface it is running in (from the env
 * cmux sets in every terminal). The daemon watches that directory, groups
 * sessions by workspace, and paints the deck.
 *
 * States: working | waiting | blocked | compacting | idle | ended
 *
 * Subagents: the subagent extension spawns children as `pi -p --mode json`,
 * which inherit this process's env. We stamp our session id into
 * PI_DECK_PARENT, so any child recognises itself as a subagent and reports who
 * spawned it — the daemon then nests it under the parent's key instead of
 * giving it one of its own.
 */

import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const exec = promisify(execFile);

const HEARTBEAT_MS = 15_000;
const MIN_WRITE_MS = 200;

type State = "working" | "waiting" | "blocked" | "compacting" | "idle" | "ended";
type Role = "main" | "subagent";

const PARENT_ENV = "PI_DECK_PARENT";

interface Snapshot {
  v: 1;
  sessionId: string;
  pid: number;
  state: State;
  role: Role;
  parentSessionId?: string;
  label: string;
  branch?: string;
  activity?: string;
  cwd: string;
  model?: string;
  cmux: { workspaceId?: string; surfaceId?: string; paneId?: string };
  startedAt: number;
  stateSince: number;
  updatedAt: number;
}

function home(): string {
  return process.env.PI_DECK_HOME ?? path.join(os.homedir(), ".pi-deck");
}

function statusDir(): string {
  return path.join(home(), "status");
}

export default function (pi: ExtensionAPI) {
  let state: State = "idle";
  let stateSince = Date.now() / 1000;
  let activity: string | undefined;
  let label = path.basename(process.cwd());
  let branch: string | undefined;
  let sessionId = `pid-${process.pid}`;
  let cwd = process.cwd();
  let model: string | undefined;
  let role: Role = "main";
  let parentSessionId: string | undefined;
  let taskLabelled = false;
  let file: string | undefined;
  let heartbeat: NodeJS.Timeout | undefined;
  let lastWrite = 0;
  let pendingWrite: NodeJS.Timeout | undefined;
  const startedAt = Date.now() / 1000;

  const snapshot = (): Snapshot => ({
    v: 1,
    sessionId,
    pid: process.pid,
    state,
    role,
    parentSessionId,
    label,
    branch,
    activity,
    cwd,
    model,
    cmux: {
      workspaceId: process.env.CMUX_WORKSPACE_ID,
      surfaceId: process.env.CMUX_SURFACE_ID,
      paneId: process.env.CMUX_PANEL_ID,
    },
    startedAt,
    stateSince,
    updatedAt: Date.now() / 1000,
  });

  function writeNow(): void {
    if (!file) return;
    lastWrite = Date.now();
    const tmp = `${file}.${process.pid}.tmp`;
    try {
      fs.mkdirSync(statusDir(), { recursive: true });
      fs.writeFileSync(tmp, JSON.stringify(snapshot()));
      fs.renameSync(tmp, file);
    } catch {
      // The deck is a nicety; never let it break a session.
    }
  }

  /** Coalesce chatty events (tool churn) into at most one write per tick. */
  function write(immediate = false): void {
    if (!file) return;
    if (immediate) {
      if (pendingWrite) {
        clearTimeout(pendingWrite);
        pendingWrite = undefined;
      }
      writeNow();
      return;
    }
    const wait = Math.max(0, MIN_WRITE_MS - (Date.now() - lastWrite));
    if (wait === 0) {
      writeNow();
      return;
    }
    if (!pendingWrite) {
      pendingWrite = setTimeout(() => {
        pendingWrite = undefined;
        writeNow();
      }, wait);
      pendingWrite.unref?.();
    }
  }

  function setState(next: State, nextActivity?: string | null): void {
    const changed = next !== state;
    if (changed) {
      state = next;
      stateSince = Date.now() / 1000;
    }
    if (nextActivity !== undefined) activity = nextActivity ?? undefined;
    write(changed);
  }

  async function git(args: string[]): Promise<string | undefined> {
    try {
      const { stdout } = await exec("git", args, { cwd });
      return stdout.trim() || undefined;
    } catch {
      return undefined;   // not a repo, or no commits yet
    }
  }

  async function resolveLabel(ctx: ExtensionContext): Promise<void> {
    cwd = ctx.cwd ?? process.cwd();
    // Resolved independently: a repo with no commits still has a name.
    const [top, head] = await Promise.all([
      git(["rev-parse", "--show-toplevel"]),
      git(["rev-parse", "--abbrev-ref", "HEAD"]),
    ]);
    label = (top ? path.basename(top) : path.basename(cwd)) || cwd;
    branch = head;
    const name = pi.getSessionName?.();
    if (name) label = name;
    model = ctx.model?.id;
  }

  pi.on("session_start", async (_event, ctx) => {
    sessionId = ctx.sessionManager?.getSessionId?.() ?? sessionId;
    file = path.join(statusDir(), `${sessionId.replace(/[^\w.-]/g, "_")}.json`);
    // A session we inherited a parent marker from, or any headless run, is a
    // helper rather than something you sit in front of.
    parentSessionId = process.env[PARENT_ENV];
    role = parentSessionId || ctx.hasUI === false ? "subagent" : "main";
    process.env[PARENT_ENV] = sessionId;      // children nest under us
    await resolveLabel(ctx);
    setState("idle");
    write(true);
    if (!heartbeat) {
      heartbeat = setInterval(() => write(true), HEARTBEAT_MS);
      heartbeat.unref?.();
    }
  });

  pi.on("session_info_changed", async (event) => {
    if (event.name) label = event.name;
    write(true);
  });

  pi.on("model_select", (event) => {
    model = event.model?.id;
    write();
  });

  // MARK: - working

  pi.on("before_agent_start", (event: { prompt?: string }) => {
    // A subagent's repo name is its parent's; what it was *asked to do* is the
    // only useful label, and the first prompt is exactly that.
    if (role === "subagent" && !taskLabelled && event.prompt) {
      label = summarise(event.prompt);
      taskLabelled = true;
    }
    setState("working", "thinking");
  });

  pi.on("turn_start", () => {
    if (state !== "compacting") setState("working");
  });

  pi.on("tool_execution_start", (event: { toolName?: string; input?: Record<string, unknown> }) => {
    setState("working", describeTool(event));
  });

  pi.on("tool_execution_end", () => {
    if (state === "working") setState("working", "thinking");
  });

  pi.on("session_before_compact", () => {
    setState("compacting", "compacting context");
  });

  pi.on("session_compact", () => {
    setState("working", "thinking");
  });

  // MARK: - your move

  pi.on("agent_settled", () => {
    setState("waiting", null);
  });

  pi.on("session_shutdown", () => {
    if (heartbeat) {
      clearInterval(heartbeat);
      heartbeat = undefined;
    }
    setState("ended", null);
    write(true);
  });
}

/** First meaningful words of a prompt, for labelling a subagent's key. */
function summarise(prompt: string): string {
  const line = prompt
    .replace(/^\s*Task:\s*/i, "")
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.length > 0);
  return (line ?? "subagent").slice(0, 32);
}

/** A short, human-readable "what is it doing right now" line for the key. */
function describeTool(event: { toolName?: string; input?: Record<string, unknown> }): string {
  const name = event.toolName ?? "tool";
  const input = event.input ?? {};
  const detail =
    typeof input.command === "string"
      ? input.command
      : typeof input.path === "string"
        ? path.basename(input.path)
        : typeof input.pattern === "string"
          ? input.pattern
          : undefined;
  if (!detail) return name;
  const short = detail.split("\n")[0].slice(0, 40);
  return `${name}: ${short}`;
}
