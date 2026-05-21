// About / Help page.
// Information about the project, the team and the technology.

import { Github, Users, GraduationCap, Cpu } from 'lucide-react';

const team = [
  { initial: 'A', name: 'Alaa Aldrobe' },
  { initial: 'M', name: 'Manol Draganov' },
  { initial: 'D', name: 'Diego Baez de la Cruz' },
  { initial: 'R', name: 'Rienat Zhuravlov' },
  { initial: 'F', name: 'Fatmanur Vardar' },
];

export default function About() {
  return (
    <div className="space-y-6">
      <header className="card p-6 text-center space-y-2">
        <div className="text-4xl">🥦</div>
        <h1 className="text-2xl font-bold">Broccoli Crown Detection</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Version 1.0 - Proof of Concept
        </p>
      </header>

      {/* About the app. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-2 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-broccoli-600" />
          About this application
        </h2>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          This app uses a YOLOv8n deep learning model to find broccoli
          crowns in field images and estimate their size. It helps farmers
          decide when to harvest, based on the crown diameter.
        </p>
      </section>

      {/* Team. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <Users className="w-5 h-5 text-broccoli-600" />
          Team - Group B4
        </h2>
        <ul className="space-y-2">
          {team.map((member) => (
            <li key={member.name} className="flex items-center gap-3">
              <span className="w-8 h-8 rounded-full bg-broccoli-100 dark:bg-broccoli-900/40 text-broccoli-700 dark:text-broccoli-300 flex items-center justify-center font-semibold text-sm">
                {member.initial}
              </span>
              <span>{member.name}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Project info. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <GraduationCap className="w-5 h-5 text-broccoli-600" />
          Project info
        </h2>
        <dl className="text-sm space-y-2">
          <Row label="Program" value="Applied AI Minor" />
          <Row label="School" value="Inholland University, Haarlem" />
          <Row
            label="Client"
            value="Robotics | Smart Farming (Alkmaar)"
          />
          <Row label="Year" value="2025 - 2026" />
          <Row label="Deliverable" value="D - Proof of Concept" />
        </dl>
      </section>

      {/* Source code link. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-2 flex items-center gap-2">
          <Github className="w-5 h-5 text-broccoli-600" />
          Source code
        </h2>
        <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
          The full source code is on GitHub:
        </p>
        <a
          href="https://github.com/Alaa-nl/broccoli-detector-B"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-broccoli-700 dark:text-broccoli-400 hover:underline break-all"
        >
          github.com/Alaa-nl/broccoli-detector-B
        </a>
      </section>

      {/* Acknowledgements. */}
      <section className="card p-5 bg-broccoli-50 dark:bg-gray-800 border-broccoli-200 dark:border-broccoli-900">
        <h2 className="font-semibold mb-2 text-broccoli-900 dark:text-broccoli-300">
          Acknowledgements
        </h2>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          With thanks to Dr. Jeroen Wildenbeest, Kristel van Ammers and
          Surya Giri for guidance and the dataset. Built with Ultralytics
          YOLOv8, FastAPI and React.
        </p>
      </section>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}
