// Top header with the app name and a small broccoli icon.

import { Sprout } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Header() {
  return (
    <header className="bg-broccoli-600 text-white shadow-md">
      <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
        <Sprout className="w-7 h-7" />
        <Link to="/" className="text-xl font-bold tracking-tight">
          BroccoliDetect
        </Link>
        <span className="ml-auto text-xs bg-broccoli-700 px-2 py-1 rounded-full">
          PoC v1.0
        </span>
      </div>
    </header>
  );
}
