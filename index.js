import "dotenv/config";

import { generateText } from "./src/openai.js";

console.log(await generateText("Give me 5 ideas for a sci-fi short story."));
