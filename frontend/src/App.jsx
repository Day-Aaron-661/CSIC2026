import React, { useState } from 'react';
import NewcomerView from './features/newcomer/NewcomerView.jsx';
import MentorView from './features/mentor/MentorView.jsx';

export default function App() {
  const [role, setRole] = useState('newcomer');
  return <main>
    <header><h1>CP2 Onboarding Assistant</h1><p>Team scaffold · shared API · two-person workflow</p></header>
    <nav aria-label="Choose demo view">
      <button className={role === 'newcomer' ? '' : 'secondary'} onClick={() => setRole('newcomer')}>Newcomer</button>
      <button className={role === 'mentor' ? '' : 'secondary'} onClick={() => setRole('mentor')}>Mentor</button>
    </nav>
    <div className="notice">Scaffold only: AI responses are explicitly labeled placeholders. No authentication, retrieval or citations yet. Do not use real confidential documents.</div>
    {role === 'newcomer' ? <NewcomerView /> : <MentorView />}
  </main>;
}
