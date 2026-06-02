// Tests for Results' defensive rendering: a malformed detection payload
// (missing crowns, missing scalars) must render without throwing.

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Results from './Results.jsx';

function renderResults(detection) {
  return render(
    <MemoryRouter>
      <Results detection={detection} />
    </MemoryRouter>,
  );
}

describe('Results defensive rendering', () => {
  it('shows the empty-state when no detection is provided', () => {
    renderResults(null);
    expect(screen.getByText(/no results yet/i)).toBeInTheDocument();
  });

  it('renders without crashing when crowns and scalars are missing', () => {
    // An object that parsed fine but lacks the expected fields.
    renderResults({});

    // It reaches the results view (not the no-results fallback)...
    expect(screen.getByText('Detection Results')).toBeInTheDocument();
    // ...and treats the missing crowns as an empty list.
    expect(
      screen.getByText(/did not find any crowns/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Detected Crowns \(0\)/i)).toBeInTheDocument();
  });

  it('renders a crown row even when its numeric fields are missing', () => {
    renderResults({
      num_crowns: 1,
      crowns: [{ crown_id: 7, size_category: 'medium' }],
    });

    // The crown id still renders; missing numbers degrade to '-'.
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText(/- cm/)).toBeInTheDocument();
  });
});
