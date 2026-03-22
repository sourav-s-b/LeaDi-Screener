import React, { useState } from 'react';
import { Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import ScreeningProgress, { STEPS } from './ScreeningProgress';
import HandwritingTest  from './HandwritingTest';
import DysarthriaTest   from './DysarthriaTest';
import DyslexiaTest     from './DyslexiaTest';
import ScreeningResult  from './ScreeningResult';

interface TestResult { risk: number; label: string; result?: any; }

export default function ScreeningOrchestrator() {
  const navigate  = useNavigate();
  const [results, setResults] = useState<Record<string, TestResult>>({});

  const activeStep = STEPS.findIndex(s => !results[s.id]);

  const handleComplete = (id: string, risk: number, label: string, result: any) => {
    const updated = { ...results, [id]: { risk, label, result } };
    setResults(updated);
    const nextStep = STEPS.findIndex(s => !updated[s.id]);
    navigate(nextStep === -1 ? '/screening/result' : '/screening');
  };

  const reset = () => setResults({});

  return (
    <Routes>
      <Route path="/"
        element={
          <ScreeningProgress
            results={results}
            activeStep={Math.max(0, activeStep)}
            onNext={() => navigate(STEPS[Math.max(0, activeStep)].route)}
          />
        }
      />
      {/* Step 1: Handwriting */}
      <Route path="/handwriting"
        element={
          results['handwriting'] ? <Navigate to="/screening" replace /> :
          <HandwritingTest onComplete={(r, l, res) => handleComplete('handwriting', r, l, res)} />
        }
      />
      {/* Step 2: Speech */}
      <Route path="/dysarthria"
        element={
          results['dysarthria'] ? <Navigate to="/screening" replace /> :
          !results['handwriting'] ? <Navigate to="/screening" replace /> :
          <DysarthriaTest onComplete={(r, l, res) => handleComplete('dysarthria', r, l, res)} />
        }
      />
      {/* Step 3: Eye Tracking */}
      <Route path="/dyslexia"
        element={
          results['dyslexia'] ? <Navigate to="/screening" replace /> :
          !results['dysarthria'] ? <Navigate to="/screening" replace /> :
          <DyslexiaTest onComplete={(r, l, res) => handleComplete('dyslexia', r, l, res)} />
        }
      />
      <Route path="/result"
        element={
          Object.keys(results).length < 3 ? <Navigate to="/screening" replace /> :
          <ScreeningResult results={results} onReset={reset} />
        }
      />
    </Routes>
  );
}
