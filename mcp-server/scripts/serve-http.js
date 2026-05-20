const { runPython } = require("./python-bin");

process.env.PROMPTBANKEN_MCP_MODE = process.env.PROMPTBANKEN_MCP_MODE || "hosted";

runPython(["-m", "server.http_server"]);
