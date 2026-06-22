import "dotenv/config";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  checkConductor,
  completeDmChoice,
  ensureWorkflowRegistered,
  getExecution,
  startQuest,
} from "./conductor-cli.js";
import { buildGameState } from "./game-state.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.PORT) || 3456;

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

app.get("/api/health", async (_req, res) => {
  try {
    const cmd = await checkConductor();
    res.json({ ok: true, conductorCmd: cmd });
  } catch (err) {
    res.status(503).json({ ok: false, error: err.message });
  }
});

app.post("/api/quest/start", async (req, res) => {
  try {
    await ensureWorkflowRegistered();
    const inputFile = req.body?.inputFile || "sample_quest_input.json";
    const workflowId = await startQuest(inputFile);
    const execution = await getExecution(workflowId);
    res.json(buildGameState(execution));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/quest/:id", async (req, res) => {
  try {
    const execution = await getExecution(req.params.id);
    res.json(buildGameState(execution));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/quest/:id/choose", async (req, res) => {
  try {
    const { approach, dmNotes = "" } = req.body ?? {};
    const valid = ["stealth", "assault", "parley"];
    if (!valid.includes(approach)) {
      res.status(400).json({ error: `approach must be one of: ${valid.join(", ")}` });
      return;
    }

    await completeDmChoice(req.params.id, approach, dmNotes);

    // Boss fight resolves immediately after DM choice — poll until settled.
    let execution;
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      execution = await getExecution(req.params.id);
      if (execution.status !== "RUNNING") break;
      const dm = execution.tasks?.find((t) => t.referenceTaskName === "dm_crossroads_ref");
      if (dm?.status === "COMPLETED") {
        const boss = execution.tasks?.find((t) => t.referenceTaskName === "boss_ref");
        if (boss?.status === "COMPLETED" || execution.status !== "RUNNING") break;
      }
    }

    res.json(buildGameState(execution));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`D&D Quest Game → http://localhost:${PORT}`);
  console.log(`Using conductor: ${process.env.CONDUCTOR_CMD || "conductor"}`);
});
