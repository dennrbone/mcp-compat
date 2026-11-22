import { appendFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const directory = process.cwd();
const record = (request) => appendFileSync(join(directory, "requests.jsonl"), JSON.stringify(request) + "\n");

if (process.env.KEYWORD_SOURCE === "firecrawl") {
  globalThis.fetch = async (url, config) => {
    if (String(url) !== "https://fixture.invalid/v2/parse" || config.method !== "POST") {
      throw new Error("Запрос за пределами тестового API");
    }
    const html = await config.body.get("file").text();
    const options = JSON.parse(config.body.get("options"));
    record({ html, options });
    return Response.json({ success: true, data: { markdown: html.replace(/<[^>]+>/g, "") } });
  };
}

if (process.env.KEYWORD_SOURCE === "randomuser") {
  const module = join(process.env.KEYWORD_PACKAGE_DIR, "node_modules", "axios", "index.js");
  const { default: axios } = await import(pathToFileURL(module));
  axios.defaults.adapter = async ({ baseURL, url, params }) => {
    if (baseURL !== "https://randomuser.me/api/" || url !== "") {
      throw new Error("Запрос за пределами тестового API");
    }
    record({ params });
    const { nat, gender, results } = params;
    return { status: 200, data: { results: Array.from({ length: results }, () => ({ nat, gender })) } };
  };
}
