export function appUrl(path) {
  return import.meta.env.BASE_URL.replace(/\/$/, '') + path;
}
