const { spawnSync } = require("child_process");

const DEFAULT_SERVICE = "promptbanken-mcp";
const DEFAULT_TAIL = "500";

function parseArgs(argv) {
  const options = {
    service: DEFAULT_SERVICE,
    tail: DEFAULT_TAIL,
    showLogs: true,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--service" && argv[index + 1]) {
      options.service = argv[index + 1];
      index += 1;
    } else if (arg === "--tail" && argv[index + 1]) {
      options.tail = argv[index + 1];
      index += 1;
    } else if (arg === "--summary-only") {
      options.showLogs = false;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }

  return options;
}

function printHelp() {
  console.log(`Usage:
  npm run logs:summary -- [--tail 500] [--service promptbanken-mcp] [--summary-only]

Examples:
  npm run logs:summary
  npm run logs:summary -- --tail 2000
  npm run logs:summary -- --summary-only
`);
}

function runComposeLogs(options) {
  const attempts = [
    { command: "docker", args: ["compose", "logs", "--tail", options.tail, options.service] },
    { command: "docker-compose", args: ["logs", "--tail", options.tail, options.service] },
  ];

  const errors = [];
  for (const attempt of attempts) {
    const result = spawnSync(attempt.command, attempt.args, {
      cwd: process.cwd(),
      encoding: "utf8",
    });

    if (result.status === 0) {
      return result.stdout || "";
    }

    errors.push(`${attempt.command} ${attempt.args.join(" ")}\n${result.stderr || result.stdout || ""}`.trim());
  }

  throw new Error(`Could not read Docker Compose logs.\n\n${errors.join("\n\n")}`);
}

function increment(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function sortedEntries(map) {
  return [...map.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
}

function parseLogSummary(logText) {
  const lines = logText.split(/\r?\n/).filter(Boolean);
  const toolCounts = new Map();
  const promptCounts = new Map();
  let sseConnects = 0;
  let healthChecks = 0;
  let authDenied = 0;

  for (const line of lines) {
    const toolMatch = line.match(/tool_call name=([a-zA-Z0-9_]+)/);
    if (toolMatch) {
      const toolName = toolMatch[1];
      increment(toolCounts, toolName);

      const skillMatch = line.match(/\bskill_id=([a-zA-Z0-9_-]+)/);
      if (toolName === "get_skill" && skillMatch) {
        increment(promptCounts, skillMatch[1]);
      }
    }

    if (line.includes("sse_connect path=/sse")) {
      sseConnects += 1;
    }
    if (line.includes("http_request path=/healthz status=200")) {
      healthChecks += 1;
    }
    if (line.includes("auth_denied")) {
      authDenied += 1;
    }
  }

  return {
    authDenied,
    healthChecks,
    lines,
    promptCounts,
    sseConnects,
    toolCounts,
  };
}

function printTable(title, entries, emptyText) {
  console.log(`\n${title}`);
  if (entries.length === 0) {
    console.log(`  ${emptyText}`);
    return;
  }

  const nameWidth = Math.max(...entries.map(([name]) => name.length), 4);
  for (const [name, count] of entries) {
    console.log(`  ${name.padEnd(nameWidth)}  ${count}`);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const logs = runComposeLogs(options);
  const summary = parseLogSummary(logs);

  if (options.showLogs) {
    console.log(`Recent logs, service=${options.service}, tail=${options.tail}`);
    console.log(logs.trim() || "(no logs)");
  }

  console.log("\nSummary");
  console.log(`  log_lines       ${summary.lines.length}`);
  console.log(`  tool_calls      ${[...summary.toolCounts.values()].reduce((sum, value) => sum + value, 0)}`);
  console.log(`  sse_connects    ${summary.sseConnects}`);
  console.log(`  health_checks   ${summary.healthChecks}`);
  console.log(`  auth_denied     ${summary.authDenied}`);

  printTable("Tool calls", sortedEntries(summary.toolCounts), "No tool calls found.");
  printTable("Top prompts", sortedEntries(summary.promptCounts).slice(0, 10), "No get_skill skill_id entries found.");
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
