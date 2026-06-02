// Tests for Results' defensive rendering: a malformed detection payload
// (missing crowns, missing scalars) must render without throwing.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Results from './Results.jsx';

// A fully-formed single-crown detection for the keyboard-toggle tests.
const oneCrown = {
  num_crowns: 1,
  num_filtered: 0,
  conf_threshold: 0.4,
  aspect_ratio_filter: true,
  camera_height_mm: 1000,
  inference_time_ms: 42,
  image_width: 320,
  image_height: 240,
  annotated_url: '/uploads/x_annotated.png',
  crowns: [
    {
      crown_id: 1,
      bbox: { x1: 10, y1: 20, x2: 110, y2: 120 },
      confidence: 0.9,
      diameter_mm: 85,
      diameter_cm: 8.5,
      size_category: 'medium',
    },
  ],
};

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

describe('Results crown-row keyboard access', () => {
  it('exposes each crown row as a button with aria-expanded', () => {
    renderResults(oneCrown);

    const row = screen.getByRole('button', { expanded: false });
    expect(row).toHaveAttribute('tabindex', '0');
    // The "(" distinguishes the crown detail from the disclaimer prose.
    expect(screen.queryByText(/Bounding box: \(/i)).not.toBeInTheDocument();
  });

  it('toggles details with the Enter key', async () => {
    const user = userEvent.setup();
    renderResults(oneCrown);

    const row = screen.getByRole('button');
    row.focus();

    await user.keyboard('{Enter}');
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Bounding box: \(/i)).toBeInTheDocument();

    await user.keyboard('{Enter}');
    expect(row).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Bounding box: \(/i)).not.toBeInTheDocument();
  });

  it('toggles details with the Space key', async () => {
    const user = userEvent.setup();
    renderResults(oneCrown);

    const row = screen.getByRole('button');
    row.focus();

    await user.keyboard(' ');
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Bounding box: \(/i)).toBeInTheDocument();
  });
});
