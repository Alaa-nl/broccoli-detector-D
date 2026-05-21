// Home / Dashboard page.
// Shows quick action cards to navigate to the main features.

import { Link } from 'react-router-dom';
import { Upload, Settings, Info, Camera } from 'lucide-react';

// Each tile is a Link to one of the main screens.
const tiles = [
  {
    to: '/upload',
    label: 'Upload Image',
    description: 'Send a broccoli photo for detection.',
    icon: Upload,
    primary: true,
  },
  {
    to: '/settings',
    label: 'Settings',
    description: 'Theme and camera height.',
    icon: Settings,
  },
  {
    to: '/about',
    label: 'About & Help',
    description: 'How it works, team, contact.',
    icon: Info,
  },
];

export default function Home() {
  return (
    <div className="space-y-6">
      {/* Welcome banner. */}
      <section className="card p-6">
        <div className="flex items-start gap-4">
          <Camera className="w-10 h-10 text-broccoli-600 flex-shrink-0" />
          <div>
            <h1 className="text-2xl font-bold mb-2">Welcome to BroccoliDetect</h1>
            <p className="text-gray-600 dark:text-gray-300 leading-relaxed">
              A simple tool that helps farmers and researchers find broccoli
              crowns in field images and check their size. Upload a photo
              to get started.
            </p>
          </div>
        </div>
      </section>

      {/* Quick action tiles. */}
      <section>
        <h2 className="text-sm font-semibold uppercase text-gray-500 dark:text-gray-400 mb-3 tracking-wider">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {tiles.map(({ to, label, description, icon: Icon, primary }) => (
            <Link
              key={to}
              to={to}
              className={`card p-5 hover:shadow-md transition-all group ${
                primary ? 'ring-2 ring-broccoli-500' : ''
              }`}
            >
              <Icon
                className={`w-8 h-8 mb-3 transition-transform group-hover:scale-110 ${
                  primary
                    ? 'text-broccoli-600'
                    : 'text-gray-500 dark:text-gray-400'
                }`}
              />
              <div className="font-semibold text-lg">{label}</div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {description}
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Simple stats / facts card to fill the space. */}
      <section className="card p-5 bg-broccoli-50 dark:bg-gray-800 border-broccoli-200 dark:border-broccoli-900">
        <h3 className="font-semibold mb-2 text-broccoli-800 dark:text-broccoli-300">
          How the model performs
        </h3>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The YOLOv8n model reached <strong>mAP@0.5 = 0.976</strong> and
          <strong> mean IoU = 0.916</strong> on a test set of 27 unseen
          field images during Deliverable B training.
        </p>
      </section>
    </div>
  );
}
