// Tests that Home renders its model metrics from the shared MODEL_INFO
// source, so the page text can't silently drift from the single source.

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Home from './Home.jsx';
import { MODEL_INFO } from '../constants/model.js';

describe('Home model metrics', () => {
  it('renders the metrics from MODEL_INFO', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    );

    // The prose is split across <strong> and interpolated nodes, so match the
    // whole paragraph by one metric, then assert the rest live in it too.
    const para = screen.getByText(
      (_content, el) =>
        el?.tagName.toLowerCase() === 'p' &&
        el.textContent.includes(`mAP@0.5 = ${MODEL_INFO.trainingMap}`),
    );
    expect(para.textContent).toContain(`mean IoU = ${MODEL_INFO.meanIoU}`);
    expect(para.textContent).toContain(`${MODEL_INFO.testSetSize} unseen`);
  });
});
