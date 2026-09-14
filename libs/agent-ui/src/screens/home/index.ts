import type { ScreenModule } from '../types';
import { HomeScreen } from './home-screen';

/** The empty state — nothing open. */
export const homeScreen: ScreenModule = {
  key: 'home',
  displayName: 'Home',
  Center: HomeScreen,
};
