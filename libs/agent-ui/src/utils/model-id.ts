/** Combine a `ModelCard`'s `provider` + `id` into the `"{provider}:{model}"`
 * form the backend expects wherever a model is selected (`ModelSelection.model_id`,
 * `CreateChatRequest.model_id`, `UpdateChatModelRequest.model_id`). */
export function composeModelId(provider: string, model: string): string {
  return `${provider}:${model}`;
}
