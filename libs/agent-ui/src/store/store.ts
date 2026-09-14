import { configureStore } from '@reduxjs/toolkit';

import chatReducer from './chat-slice';
import workspaceReducer from './workspace-slice';
import type { RootState } from './types';

export const store = configureStore({
  reducer: {
    chat: chatReducer,
    workspace: workspaceReducer,
  },
});

// `RootState` is hand-declared in `./types` (so the slices can type their thunks
// without importing back from here). This asserts, at compile time, that it
// still matches the store the reducers actually build — add or rename a reducer
// without updating `./types` and this assignment stops type-checking.
type StoreShape = ReturnType<typeof store.getState>;
const _rootStateInSync: RootState extends StoreShape
  ? StoreShape extends RootState
    ? true
    : never
  : never = true;
void _rootStateInSync;

export type { RootState };
export type AppDispatch = typeof store.dispatch;
