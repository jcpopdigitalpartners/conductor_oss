import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");

function parseConductorCmd() {
  const raw = process.env.CONDUCTOR_CMD || "conductor";
  return raw.trim().split(/\s+/);
}

function runConductor(args, { cwd = PROJECT_ROOT } = {}) {
  const parts = parseConductorCmd();
  const cmd = parts[0];
  const prefixArgs = parts.slice(1);

  return new Promise((resolve, reject) => {
    const child = spawn(cmd, [...prefixArgs, ...args], {
      cwd,
      env: process.env,
      shell: process.platform === "win32" && !process.env.CONDUCTOR_CMD,
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        const message = (stderr || stdout || `conductor exited with code ${code}`).trim();
        reject(new Error(message));
        return;
      }
      resolve(stdout);
    });
  });
}

function stripCliNoise(output) {
  return output
    .split("\n")
    .filter((line) => !line.startsWith("Auto-detected Conductor"))
    .join("\n")
    .trim();
}

function extractWorkflowId(output) {
  const cleaned = stripCliNoise(output);
  const match = cleaned.match(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
  );
  if (!match) {
    throw new Error(`Could not parse workflow id from:\n${cleaned}`);
  }
  return match[0];
}

function parseJsonOutput(output) {
  const cleaned = stripCliNoise(output);
  const start = cleaned.indexOf("{");
  const end = cleaned.lastIndexOf("}");
  if (start === -1 || end === -1) {
    throw new Error(`Expected JSON in conductor output:\n${cleaned}`);
  }
  return JSON.parse(cleaned.slice(start, end + 1));
}

export async function ensureWorkflowRegistered() {
  await runConductor([
    "workflow",
    "create",
    path.join(PROJECT_ROOT, "dnd_quest_pipeline.json"),
  ]).catch(() => {
    // already registered is fine
  });
}

export async function startQuest(inputFile = "sample_quest_input.json") {
  const filePath = path.join(PROJECT_ROOT, inputFile);
  const output = await runConductor([
    "workflow",
    "start",
    "-w",
    "dnd_quest_pipeline",
    "-f",
    filePath,
  ]);
  return extractWorkflowId(output);
}

export async function getExecution(workflowId) {
  const output = await runConductor([
    "workflow",
    "get-execution",
    workflowId,
    "-c",
  ]);
  return parseJsonOutput(output);
}

export async function completeDmChoice(workflowId, approach, dmNotes = "") {
  const output = JSON.stringify({ approach, dmNotes });
  await runConductor([
    "task",
    "update-execution",
    "--workflow-id",
    workflowId,
    "--task-ref-name",
    "dm_crossroads_ref",
    "--status",
    "COMPLETED",
    "--output",
    output,
  ]);
}

export async function checkConductor() {
  await runConductor(["--version"]);
  return parseConductorCmd().join(" ");
}
