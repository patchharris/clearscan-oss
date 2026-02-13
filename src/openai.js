import OpenAI from "openai";

export const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function generateText(prompt) {
  const res = await openai.responses.create({
    model: "gpt-4.1-mini",
    input: prompt,
  });
  return res.output_text;
}
