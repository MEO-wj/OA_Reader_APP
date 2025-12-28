// Metro 配置：在 Windows 上降低并发，避免 EMFILE（too many open files）
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

const maxWorkersFromEnv = Number(process.env.METRO_MAX_WORKERS);
config.maxWorkers =
  Number.isFinite(maxWorkersFromEnv) && maxWorkersFromEnv > 0 ? maxWorkersFromEnv : 2;

module.exports = config;
