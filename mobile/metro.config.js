// This app lives inside the web app's repository. Resolve packages only from mobile/node_modules, so the web app's
// own copy of React in the parent folder can never end up in the phone bundle.
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);
config.resolver.disableHierarchicalLookup = true;
config.resolver.nodeModulesPaths = [path.resolve(__dirname, "node_modules")];
config.watchFolders = [__dirname];

module.exports = config;
