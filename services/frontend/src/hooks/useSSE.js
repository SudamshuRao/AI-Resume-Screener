import { useEffect, useState } from "react";

export const AGENT_STEPS = [
  { key: "resume_parser",      label: "Parsing resume",             icon: "📄" },
  { key: "jd_analyst",         label: "Analyzing job description",  icon: "🔍" },
  { key: "company_researcher", label: "Researching company",        icon: "🏢" },
  { key: "gap_analyst",        label: "Running gap analysis",       icon: "📊" },
  { key: "resume_tailor",      label: "Tailoring resume bullets",   icon: "✏️"  },
  { key: "cover_letter",       label: "Writing cover letter",       icon: "✉️"  },
  { key: "interview_coach",    label: "Preparing interview Q&A",    icon: "🎯" },
];

// How long to simulate each step before the real response arrives.
// 7 steps × 7 s = ~49 s ceiling before we stall at step 6 waiting for the LLM.
const STEP_INTERVAL_MS = 7000;

/**
 * Simulates pipeline progress while a blocking /analyze call is in flight.
 *
 * - Advances one step every STEP_INTERVAL_MS ms, but stalls at the last step
 *   until `isDone` is true so we never claim 100% before the work is done.
 * - When `isDone` flips to true the hook immediately jumps to 100%.
 */
export function useSimulatedProgress(isActive, isDone) {
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    if (!isActive) {
      setCurrentStep(0);
      return;
    }

    // Real work finished — snap to 100 %
    if (isDone) {
      setCurrentStep(AGENT_STEPS.length);
      return;
    }

    // Stall at the last step until the actual response arrives
    if (currentStep >= AGENT_STEPS.length - 1) return;

    const timer = setTimeout(
      () => setCurrentStep((s) => s + 1),
      STEP_INTERVAL_MS
    );
    return () => clearTimeout(timer);
  }, [isActive, isDone, currentStep]);

  const progress = currentStep / AGENT_STEPS.length; // 0.0 – 1.0
  return { currentStep, progress };
}