import { describe, expect, it } from 'vitest';
import type { Agent, Chat, Project } from '@krutrim_agent/shared-types';

import workspaceReducer, {
  clearSelection,
  createNewAgent,
  createNewChat,
  createNewProject,
  deleteAgentById,
  deleteChatById,
  deleteProjectById,
  fetchWorkspace,
  moveChatToProject,
  openAgent,
  selectChat,
  setBackendUrl,
  toggleProjectExpanded,
  type WorkspaceState,
} from '../src/store/workspace-slice';

// Same approach as chat-slice.test.ts: RTK's async-thunk `.pending` /
// `.fulfilled` / `.rejected` action creators let extraReducers be exercised
// with real, correctly-typed actions without touching the `../api` layer.

function project(overrides: Partial<Project> = {}): Project {
  return {
    project_id: 'p1',
    user_id: 'u1',
    project_title: 'Project 1',
    project_information: '',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sandbox_sharing: 'isolated',
    sandbox_idle_timeout_seconds: null,
    sandbox_resource_overrides: null,
    ...overrides,
  };
}

function agent(overrides: Partial<Agent> = {}): Agent {
  return {
    agent_id: 'a1',
    user_id: 'u1',
    project_id: 'p1',
    agent_key: 'research',
    display_name: 'Agent 1',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sandbox_sharing: null,
    sandbox_idle_timeout_seconds: null,
    sandbox_resource_overrides: null,
    ...overrides,
  } as Agent;
}

function chat(overrides: Partial<Chat> = {}): Chat {
  return {
    chat_id: 'c1',
    user_id: 'u1',
    project_id: null,
    display_name: 'Chat 1',
    provider: 'openrouter',
    model: 'model-x',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    sandbox_sharing: null,
    sandbox_idle_timeout_seconds: null,
    sandbox_resource_overrides: null,
    ...overrides,
  };
}

const initial: WorkspaceState = workspaceReducer(undefined, { type: '@@init' });

describe('workspace-slice plain reducers', () => {
  it('setBackendUrl stores the backend URL', () => {
    expect(workspaceReducer(initial, setBackendUrl('http://backend.example')).backendUrl).toBe(
      'http://backend.example',
    );
  });

  it('toggleProjectExpanded adds then removes a project id', () => {
    const expanded = workspaceReducer(initial, toggleProjectExpanded('p1'));
    expect(expanded.expandedProjectIds).toEqual(['p1']);
    const collapsed = workspaceReducer(expanded, toggleProjectExpanded('p1'));
    expect(collapsed.expandedProjectIds).toEqual([]);
  });

  it('selectChat / clearSelection set and clear the selection', () => {
    const selected = workspaceReducer(initial, selectChat('c1'));
    expect(selected.selection).toEqual({ kind: 'chat', chatId: 'c1' });
    expect(workspaceReducer(selected, clearSelection()).selection).toBeNull();
  });
});

describe('workspace-slice fetchWorkspace', () => {
  it('marks isLoading while pending and hasLoaded + data on fulfilled', () => {
    const pending = workspaceReducer(initial, fetchWorkspace.pending('reqId', undefined));
    expect(pending.isLoading).toBe(true);
    expect(pending.hasLoaded).toBe(false);

    const projects = [project()];
    const fulfilled = workspaceReducer(
      pending,
      fetchWorkspace.fulfilled(
        {
          projects,
          agentsByProject: { p1: [agent()] },
          chatsByProject: { p1: [] },
          standaloneChats: [],
          agentProfiles: [],
        },
        'reqId',
        undefined,
      ),
    );
    expect(fulfilled.isLoading).toBe(false);
    expect(fulfilled.hasLoaded).toBe(true);
    expect(fulfilled.projects).toBe(projects);
  });

  it('marks hasLoaded true even on rejected, so a deep link is not bounced to "/" prematurely', () => {
    const state = workspaceReducer(
      { ...initial, isLoading: true },
      fetchWorkspace.rejected(new Error('x'), 'reqId', undefined, 'Failed to load the workspace.'),
    );
    expect(state.isLoading).toBe(false);
    expect(state.hasLoaded).toBe(true);
    expect(state.error).toBe('Failed to load the workspace.');
  });
});

describe('workspace-slice project lifecycle', () => {
  it('createNewProject.fulfilled expands the new project', () => {
    const state = workspaceReducer(
      initial,
      createNewProject.fulfilled(project({ project_id: 'p-new' }), 'reqId', 'title'),
    );
    expect(state.expandedProjectIds).toEqual(['p-new']);
  });

  it('deleteProjectById.fulfilled removes the project, its agents/chats, and clears a now-dangling agent selection', () => {
    const loaded: WorkspaceState = {
      ...initial,
      projects: [project()],
      agentsByProject: { p1: [agent()] },
      chatsByProject: { p1: [] },
      selection: { kind: 'agent', agentId: 'a1', sessionId: 's1' },
    };
    const state = workspaceReducer(loaded, deleteProjectById.fulfilled('p1', 'reqId', 'p1'));
    expect(state.projects).toEqual([]);
    expect(state.agentsByProject['p1']).toBeUndefined();
    expect(state.chatsByProject['p1']).toBeUndefined();
    expect(state.selection).toBeNull();
  });

  it('deleteProjectById.fulfilled leaves an unrelated selection untouched', () => {
    const loaded: WorkspaceState = {
      ...initial,
      projects: [project()],
      agentsByProject: { p1: [agent()] },
      chatsByProject: {},
      selection: { kind: 'chat', chatId: 'c-standalone' },
    };
    const state = workspaceReducer(loaded, deleteProjectById.fulfilled('p1', 'reqId', 'p1'));
    expect(state.selection).toEqual({ kind: 'chat', chatId: 'c-standalone' });
  });
});

describe('workspace-slice agent lifecycle', () => {
  it('createNewAgent.fulfilled appends the agent, expands its project, and selects it', () => {
    const state = workspaceReducer(
      { ...initial, agentsByProject: {} },
      createNewAgent.fulfilled(
        { agent: agent({ agent_id: 'a-new' }), sessionId: 's1' },
        'reqId',
        { projectId: 'p1', agentKey: 'research', displayName: 'New Agent' },
      ),
    );
    expect(state.agentsByProject['p1']?.map((a) => a.agent_id)).toEqual(['a-new']);
    expect(state.expandedProjectIds).toEqual(['p1']);
    expect(state.selection).toEqual({ kind: 'agent', agentId: 'a-new', sessionId: 's1' });
  });

  it('deleteAgentById.fulfilled removes the agent and clears its own selection, but not another agent selection', () => {
    const loaded: WorkspaceState = {
      ...initial,
      agentsByProject: { p1: [agent({ agent_id: 'a1' }), agent({ agent_id: 'a2' })] },
      selection: { kind: 'agent', agentId: 'a1', sessionId: 's1' },
    };
    const state = workspaceReducer(
      loaded,
      deleteAgentById.fulfilled({ projectId: 'p1', agentId: 'a1' }, 'reqId', { projectId: 'p1', agentId: 'a1' }),
    );
    expect(state.agentsByProject['p1']?.map((a) => a.agent_id)).toEqual(['a2']);
    expect(state.selection).toBeNull();
  });
});

describe('workspace-slice chat lifecycle', () => {
  it('createNewChat.fulfilled files a project chat under its project and selects it', () => {
    const state = workspaceReducer(
      { ...initial, chatsByProject: {} },
      createNewChat.fulfilled(chat({ chat_id: 'c-new', project_id: 'p1' }), 'reqId', { displayName: 'x', projectId: 'p1' }),
    );
    expect(state.chatsByProject['p1']?.map((c) => c.chat_id)).toEqual(['c-new']);
    expect(state.expandedProjectIds).toEqual(['p1']);
    expect(state.selection).toEqual({ kind: 'chat', chatId: 'c-new' });
  });

  it('createNewChat.fulfilled files a projectless chat under standaloneChats', () => {
    const state = workspaceReducer(
      initial,
      createNewChat.fulfilled(chat({ chat_id: 'c-new', project_id: null }), 'reqId', { displayName: 'x' }),
    );
    expect(state.standaloneChats.map((c) => c.chat_id)).toEqual(['c-new']);
    expect(state.selection).toEqual({ kind: 'chat', chatId: 'c-new' });
  });

  it('deleteChatById.fulfilled removes the chat from every list and clears its own selection', () => {
    const loaded: WorkspaceState = {
      ...initial,
      standaloneChats: [chat({ chat_id: 'c1' })],
      chatsByProject: { p1: [chat({ chat_id: 'c2', project_id: 'p1' })] },
      selection: { kind: 'chat', chatId: 'c1' },
    };
    const state = workspaceReducer(loaded, deleteChatById.fulfilled('c1', 'reqId', 'c1'));
    expect(state.standaloneChats).toEqual([]);
    expect(state.chatsByProject['p1']?.map((c) => c.chat_id)).toEqual(['c2']);
    expect(state.selection).toBeNull();
  });

  it('moveChatToProject.fulfilled moves a standalone chat into a project', () => {
    const loaded: WorkspaceState = {
      ...initial,
      standaloneChats: [chat({ chat_id: 'c1', project_id: null })],
      chatsByProject: {},
    };
    const moved = chat({ chat_id: 'c1', project_id: 'p1' });
    const state = workspaceReducer(loaded, moveChatToProject.fulfilled(moved, 'reqId', { chatId: 'c1', projectId: 'p1' }));
    expect(state.standaloneChats).toEqual([]);
    expect(state.chatsByProject['p1']?.map((c) => c.chat_id)).toEqual(['c1']);
    expect(state.expandedProjectIds).toEqual(['p1']);
  });

  it('moveChatToProject.fulfilled moves a project chat back to standalone', () => {
    const loaded: WorkspaceState = {
      ...initial,
      standaloneChats: [],
      chatsByProject: { p1: [chat({ chat_id: 'c1', project_id: 'p1' })] },
    };
    const moved = chat({ chat_id: 'c1', project_id: null });
    const state = workspaceReducer(loaded, moveChatToProject.fulfilled(moved, 'reqId', { chatId: 'c1', projectId: null }));
    expect(state.chatsByProject['p1']).toEqual([]);
    expect(state.standaloneChats.map((c) => c.chat_id)).toEqual(['c1']);
  });
});

describe('workspace-slice openAgent', () => {
  it('selects the agent + resolved session on fulfilled', () => {
    const state = workspaceReducer(
      { ...initial, error: 'previous' },
      openAgent.fulfilled({ agentId: 'a1', sessionId: 's1' }, 'reqId', { agentId: 'a1' }),
    );
    expect(state.selection).toEqual({ kind: 'agent', agentId: 'a1', sessionId: 's1' });
    expect(state.error).toBeNull();
  });

  it('records the rejection reason on rejected', () => {
    const state = workspaceReducer(
      initial,
      openAgent.rejected(new Error('x'), 'reqId', { agentId: 'a1' }, 'Unknown agent.'),
    );
    expect(state.error).toBe('Unknown agent.');
  });
});
