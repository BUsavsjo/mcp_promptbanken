const { runPython } = require("./python-bin");

process.env.PROMPTBANKEN_MCP_MODE = process.env.PROMPTBANKEN_MCP_MODE || "local";

runPython(["-m", "server.mcp_server"]);
