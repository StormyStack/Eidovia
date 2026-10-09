import { screen } from '@testing-library/react-native';

import { renderScreen } from '../../test-utils/render';
import { ARGameScreen } from '../ARGameScreen';

const CONFIG = {
  module_id: 'cell-quiz',
  scene_name: 'GameScene_CellQuiz',
  cdn_bundle_url: 'https://cdn.example.com/bundles/cell-quiz',
  difficulty: 3,
  config: { display: { description: 'Quiz' } },
};

it('shows the received scene_name and the Sprint 2 note', async () => {
  await renderScreen(ARGameScreen, 'ARGame', { config: CONFIG, title: 'Cell Quiz' });

  expect(screen.getByText('Cell Quiz')).toBeOnTheScreen();
  expect(screen.getByTestId('argame-scene-name')).toHaveTextContent('GameScene_CellQuiz');
  expect(screen.getByTestId('argame-sprint-note')).toHaveTextContent(/Unity view coming in Sprint 2/);
  expect(screen.getByText('cell-quiz')).toBeOnTheScreen();
  expect(screen.getByText('Advanced (3)')).toBeOnTheScreen();
  expect(screen.getByText('https://cdn.example.com/bundles/cell-quiz')).toBeOnTheScreen();
});
