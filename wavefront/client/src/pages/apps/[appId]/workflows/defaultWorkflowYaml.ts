// Starter YAML for a new workflow
export const DEFAULT_WORKFLOW_YAML = `metadata:
  name: content-creation-yaml-workflow
  version: 1.0.0
  description: "Content creation with YAML-defined smart router"

arium:
  agents:
    - name: content_creator
      role: "Content Creator"
      job: "Create initial content drafts on any topic with engaging style."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7

    - name: technical_writer
      role: "Technical Writer"
      job: "Specialize in technical documentation, tutorials, and educational content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

    - name: creative_writer
      role: "Creative Writer"
      job: "Specialize in creative writing, storytelling, and marketing content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.8

    - name: editor
      role: "Content Editor"
      job: "Review and polish content for clarity, flow, and quality."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

  # Router definitions in YAML
  routers:
    - name: content_router
      type: smart
      routing_options:
        technical_writer: "Handle technical documentation, tutorials, how-to guides, and educational content"
        creative_writer: "Handle creative writing, marketing copy, stories, and engaging content"
        editor: "Move to editing when content is ready for review and polishing"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        context_description: "a content creation workflow that routes based on content type and readiness"
        fallback_strategy: "first"

  workflow:
    start: content_creator
    edges:
      - from: content_creator
        to: [technical_writer, creative_writer, editor]
        router: content_router
      - from: technical_writer
        to: [editor]
      - from: creative_writer
        to: [editor]
    end: [editor]
`;
