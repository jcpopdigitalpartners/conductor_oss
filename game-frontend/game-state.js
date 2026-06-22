const STORY_TASKS = [
  { ref: "briefing_ref", label: "Tavern briefing", field: "narration" },
  { ref: "travel_roll_ref", label: "The road", field: "narration" },
  { ref: "ambush_ref", label: "Road ambush", field: "narration", optional: true },
  { ref: "merchant_ref", label: "Road merchant", field: "narration", optional: true },
  { ref: "travel_aftermath_ref", label: "Travel aftermath", field: "narration" },
  { ref: "dungeon_entry_ref", label: "Dungeon entrance", field: "narration" },
  { ref: "scout_ref", label: "Scouting — stealth", field: "intel" },
  { ref: "arcana_ref", label: "Scouting — arcana", field: "intel" },
  { ref: "religion_ref", label: "Scouting — religion", field: "intel" },
  { ref: "intel_ref", label: "Intel summary", field: "briefingForDm" },
  { ref: "stealth_approach_ref", label: "Stealth approach", field: "narration", optional: true },
  { ref: "assault_approach_ref", label: "Assault approach", field: "narration", optional: true },
  { ref: "parley_approach_ref", label: "Parley approach", field: "narration", optional: true },
  { ref: "default_approach_ref", label: "Hesitant charge", field: "narration", optional: true },
  { ref: "boss_ref", label: "Boss encounter", field: "narration" },
  { ref: "loot_ref", label: "Loot & renown", field: "epilogue", optional: true },
  { ref: "defeat_ref", label: "Retreat", field: "epilogue", optional: true },
];

function taskByRef(tasks, ref) {
  return tasks?.find((t) => t.referenceTaskName === ref);
}

function taskResult(task) {
  return task?.outputData?.result ?? task?.outputData ?? null;
}

/** Workflow TERMINATE sometimes sets epilogue to the full inline result object. */
function formatEpilogue(value) {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && typeof value.epilogue === "string") {
    return value.epilogue;
  }
  return null;
}

function lineFromTask(task, spec) {
  if (!task || task.status !== "COMPLETED") return null;
  const result = taskResult(task);
  if (!result) return null;

  let text = result[spec.field] ?? result.narration ?? null;
  text = formatEpilogue(text) ?? (typeof text === "string" ? text : null);
  if (spec.ref === "boss_ref" && result.rounds?.length) {
    const rounds = result.rounds
      .map(
        (r) =>
          `Round ${r.round}: attack ${r.attackRoll} → ${r.hit ? `${r.damageToBoss} dmg` : "miss"} | boss HP ${r.bossHp} | party HP ${r.partyHp}`
      )
      .join("\n");
    text = `${result.narration}\n${rounds}`;
  }
  if (!text) return null;
  return { label: spec.label, text };
}

export function buildGameState(execution) {
  const tasks = execution.tasks ?? [];
  const dmTask = taskByRef(tasks, "dm_crossroads_ref");
  const waitingForDm =
    dmTask?.status === "IN_PROGRESS" || dmTask?.status === "SCHEDULED";

  const log = [];
  for (const spec of STORY_TASKS) {
    const entry = lineFromTask(taskByRef(tasks, spec.ref), spec);
    if (entry) log.push(entry);
  }

  const partySheet = taskResult(taskByRef(tasks, "party_sheet_ref"));
  const intel = dmTask?.inputData?.intelReport ?? taskResult(taskByRef(tasks, "intel_ref"));

  let phase = "running";
  if (waitingForDm) phase = "dm_choice";
  else if (execution.status === "COMPLETED") phase = "victory";
  else if (execution.status === "FAILED") phase = "defeat";
  else if (execution.status === "TERMINATED") phase = "ended";

  const output = execution.output ?? {};
  const boss = taskResult(taskByRef(tasks, "boss_ref"));

  const epilogue =
    formatEpilogue(output.epilogue) ??
    formatEpilogue(taskResult(taskByRef(tasks, "loot_ref"))) ??
    formatEpilogue(taskResult(taskByRef(tasks, "defeat_ref")));

  return {
    workflowId: execution.workflowId,
    status: execution.status,
    phase,
    partyName: execution.input?.partyName,
    dungeonName: execution.input?.dungeonName,
    difficulty: execution.input?.difficulty,
    party: execution.input?.party ?? [],
    partySheet,
    intel,
    log,
    waitingForDm,
    dmInstructions: dmTask?.inputData?.instructions,
    outcome:
      output.outcome ??
      (boss?.victory === true ? "victory" : boss?.victory === false ? "defeat" : undefined),
    epilogue,
    bossFight: output.bossFight ?? boss,
    loot: taskResult(taskByRef(tasks, "loot_ref")),
    reason: execution.reasonForIncompletion,
  };
}
