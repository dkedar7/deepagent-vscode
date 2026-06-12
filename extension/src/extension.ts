import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';
import * as readline from 'readline';

/**
 * Deep Agent VS Code chat participant.
 *
 * Registers `@deepagent` in the chat panel (alongside Copilot) and bridges each
 * turn to the Python `deepagent-vscode` sidecar over stdio. The sidecar emits
 * newline-delimited JSON events — the langgraph-stream-parser `event.to_dict()`
 * wire vocabulary — which the dispatcher below maps onto the chat response.
 */
export function activate(context: vscode.ExtensionContext) {
  const participant = vscode.chat.createChatParticipant('langstage.agent', handler);
  participant.iconPath = new vscode.ThemeIcon('robot');
  context.subscriptions.push(participant);
}

export function deactivate() {}

interface AgentEvent {
  type: string;
  [key: string]: unknown;
}

async function handler(
  request: vscode.ChatRequest,
  _context: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken,
): Promise<void> {
  const config = vscode.workspace.getConfiguration('langstage');
  const legacy = vscode.workspace.getConfiguration('deepagent');
  const agentSpec =
    config.get<string>('agentSpec') || legacy.get<string>('agentSpec') || '';
  const python =
    config.get<string>('pythonPath') || legacy.get<string>('pythonPath') || 'python';

  const workspace =
    vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();

  // When the setting is empty, spawn without --agent and let the sidecar
  // resolve the family-standard chain (langstage.toml < LANGSTAGE_* env,
  // with the legacy deepagents vocabulary as fallback). If nothing resolves
  // anywhere, the sidecar emits a clean `error` event that the dispatcher
  // renders in the chat.
  const args = ['-m', 'langstage_vscode', '--workspace', workspace];
  if (agentSpec) {
    args.push('--agent', agentSpec);
  }

  const proc = spawn(python, args, {
    // cwd anchors the sidecar's langstage.toml walk-up at the workspace.
    cwd: workspace,
    env: {
      ...process.env,
      LANGSTAGE_WORKSPACE_ROOT: workspace,
      // Older sidecar versions read the legacy name.
      DEEPAGENT_WORKSPACE_ROOT: workspace,
    },
  });

  token.onCancellationRequested(() => proc.kill());

  try {
    await runTurn(proc, request.prompt, stream);
  } catch (err) {
    stream.markdown(`\n\n❌ ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    proc.kill();
  }
}

/**
 * Send one user message to the sidecar and pump its events into the chat
 * stream until the turn ends.
 */
function runTurn(
  proc: ChildProcess,
  prompt: string,
  stream: vscode.ChatResponseStream,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (!proc.stdout || !proc.stdin) {
      reject(new Error('sidecar has no stdio pipes'));
      return;
    }

    const rl = readline.createInterface({ input: proc.stdout });
    let started = false;

    rl.on('line', (line: string) => {
      const text = line.trim();
      if (!text) return;
      let event: AgentEvent;
      try {
        event = JSON.parse(text) as AgentEvent;
      } catch {
        return; // ignore non-JSON noise
      }

      // Send the message once the sidecar reports it's ready.
      if (event.type === 'ready' && !started) {
        started = true;
        proc.stdin!.write(
          JSON.stringify({ type: 'message', session_id: 'vscode', content: prompt }) + '\n',
        );
        return;
      }

      dispatch(event, stream);

      if (event.type === 'turn_end') {
        rl.close();
        resolve();
      }
    });

    proc.on('error', reject);
    proc.on('exit', () => resolve());
  });
}

/** Map one sidecar event onto the chat response stream. */
function dispatch(event: AgentEvent, stream: vscode.ChatResponseStream): void {
  switch (event.type) {
    case 'content':
      stream.markdown(String(event.content ?? ''));
      break;
    case 'reasoning':
      stream.markdown(`\n\n*${String(event.content ?? '')}*\n\n`);
      break;
    case 'tool_start':
      stream.progress(`Running \`${String(event.name ?? 'tool')}\`…`);
      break;
    case 'tool_end': {
      const status = event.status === 'error' ? '❌' : '✓';
      stream.markdown(`\n\n${status} \`${String(event.name ?? 'tool')}\`\n`);
      break;
    }
    case 'extraction':
      if (event.extracted_type === 'todos' && Array.isArray(event.data)) {
        stream.markdown('\n\n**Tasks**\n');
        for (const item of event.data as Array<Record<string, unknown>>) {
          const done = item.status === 'completed';
          const content = String(item.content ?? item.task ?? '');
          stream.markdown(`- ${done ? '[x]' : '[ ]'} ${content}\n`);
        }
      }
      break;
    case 'interrupt': {
      // HITL: v0 surfaces the requested action. The decision round-trip
      // (sending {"type":"decision",...} back to the sidecar) is the next
      // increment — it needs a confirmation affordance in the chat UI.
      const actions = (event.action_requests as Array<Record<string, unknown>>) ?? [];
      const tool = actions[0]?.tool ?? 'an action';
      stream.markdown(
        `\n\n⚠️ The agent wants to run **${String(tool)}** and is waiting for ` +
          'approval. Interactive approval is not wired up yet in this build.\n',
      );
      break;
    }
    case 'error':
      stream.markdown(`\n\n❌ ${String(event.error ?? 'unknown error')}\n`);
      break;
    // ready / ack / complete / turn_end / usage: no direct UI output.
    default:
      break;
  }
}
