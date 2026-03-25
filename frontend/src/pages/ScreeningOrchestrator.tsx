import React, { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import ScreeningProgress, { STEPS } from './ScreeningProgress';
import HandwritingTest  from './HandwritingTest';
import DysarthriaTest   from './DysarthriaTest';
import DyslexiaPage     from './Dyslexia';
import ScreeningResult  from './ScreeningResult';

interface TestResult { risk: number; label: string; result?: any; }

export default function ScreeningOrchestrator() {
  const navigate = useNavigate();
  
  // 1. Initialize state from sessionStorage so it survives the HTML redirect
  const [results, setResults] = useState<Record<string, TestResult>>(() => {
    const saved = sessionStorage.getItem('screeningOrchestratorResults');
    return saved ? JSON.parse(saved) : {};
  });

  // Active step = first step not yet completed
  const activeStep = STEPS.findIndex(s => !results[s.id]);

  // Called when a test completes OR retries (overwrites previous result)
  const handleComplete = (id: string, risk: number, label: string, result: any) => {
    const updated = { ...results, [id]: { risk, label, result } };
    setResults(updated);
    
    // 2. Save to sessionStorage whenever it updates
    sessionStorage.setItem('screeningOrchestratorResults', JSON.stringify(updated));

    const nextStep = STEPS.findIndex(s => !updated[s.id]);
    navigate(nextStep === -1 ? '/screening/result' : '/screening');
  };

  // Retry: clear one test's result so its route unlocks
  const handleRetry = (id: string) => {
    const updated = { ...results };
    delete updated[id];
    setResults(updated);
    
    // 3. Keep sessionStorage in sync
    sessionStorage.setItem('screeningOrchestratorResults', JSON.stringify(updated));
    
    const step = STEPS.find(s => s.id === id);
    if (step) navigate(step.route);
  };

  const reset = () => {
    setResults({});
    sessionStorage.removeItem('screeningOrchestratorResults');
  };

  return (
    <Routes>
      <Route path="/"
        element={
          <ScreeningProgress
            results={results}
            activeStep={Math.max(0, activeStep)}
            onNext={() => navigate(STEPS[Math.max(0, activeStep)].route)}
            onRetry={handleRetry}
          />
        }
      />
      {/* Step 1: Handwriting — allow retry even when done */}
      <Route path="/handwriting"
        element={
          <HandwritingTest
            onComplete={(r, l, res) => handleComplete('handwriting', r, l, res)}
            isRetry={!!results['handwriting']}
          />
        }
      />
      {/* Step 2: Speech */}
      <Route path="/dysarthria"
        element={
          !results['handwriting'] ? <Navigate to="/screening" replace /> :
          <DysarthriaTest
            onComplete={(r, l, res) => handleComplete('dysarthria', r, l, res)}
            isRetry={!!results['dysarthria']}
          />
        }
      />
      {/* Step 3: Eye Tracking */}
      <Route path="/dyslexia"
        element={
          !results['dysarthria'] ? <Navigate to="/screening" replace /> :
          <DyslexiaPage
            onComplete={(r, l, res) => handleComplete('dyslexia', r, l, res)}
            isRetry={!!results['dyslexia']}
          />
        }
      />
      <Route path="/result"
        element={
          Object.keys(results).length < 1 ? <Navigate to="/screening" replace /> :
          <ScreeningResult results={results} onReset={reset} onRetry={handleRetry} />
        }
      />
    </Routes>
  );
}
