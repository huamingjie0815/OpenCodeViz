import { helper } from "./helper";

export function runService() {
  helper();
  return "service";
}

function localOnly() {
  return runService();
}

export function routeHandler() {
  return localOnly();
}

