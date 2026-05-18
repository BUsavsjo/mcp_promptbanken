const { runPython } = require("./python-bin");

runPython(["-m", "server.http_server"]);
