// Not a registered screen of its own — `AgentScreen` is the shared centre pane
// that the `default` and `research` screen modules both use as their `Center`.
// The agent thread UI it renders (`AgentThread`, `AgentActivity`, …) lives here
// alongside it rather than under `components/`, since nothing else consumes it.
export { AgentScreen } from './agent-screen';
