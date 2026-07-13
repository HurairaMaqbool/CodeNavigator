"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

type VoiceInputButtonProps = {
  onTranscript: (text: string) => void;
  disabled: boolean;
};

export function VoiceInputButton({ onTranscript, disabled }: VoiceInputButtonProps) {
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [errorState, setErrorState] = useState(false);

  const recognitionRef = useRef<any>(null);
  const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSupported(false);
    }
  }, []);

  const resetSilenceTimer = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
    }
    // Auto-stop after 2.5 seconds of silence
    silenceTimerRef.current = setTimeout(() => {
      stopListening();
    }, 2500);
  };

  const startListening = async () => {
    if (!supported || disabled || listening) return;

    setErrorState(false);
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    try {
      // Check microphone permission explicitly
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Stop the test stream right away
      stream.getTracks().forEach((track) => track.stop());

      const rec = new SpeechRecognition();
      rec.lang = navigator.language || "en-US";
      rec.interimResults = true;
      rec.continuous = true;

      rec.onstart = () => {
        setListening(true);
        resetSilenceTimer();
      };

      rec.onresult = (event: any) => {
        resetSilenceTimer();
        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcriptText = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcriptText;
          } else {
            interimTranscript += transcriptText;
          }
        }

        const transcript = finalTranscript || interimTranscript;
        if (transcript.trim()) {
          onTranscript(transcript);
        }
      };

      rec.onerror = (event: any) => {
        console.error("Speech recognition error:", event.error);
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          toast.error("Microphone permission denied");
          triggerErrorState();
        }
        stopListening();
      };

      rec.onend = () => {
        stopListening();
      };

      recognitionRef.current = rec;
      rec.start();
    } catch (err) {
      console.error("Microphone permission request failed", err);
      toast.error("Microphone permission denied");
      triggerErrorState();
    }
  };

  const stopListening = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {}
      recognitionRef.current = null;
    }
    setListening(false);
  };

  const triggerErrorState = () => {
    setErrorState(true);
    setTimeout(() => {
      setErrorState(false);
    }, 1000);
  };

  const toggleListening = () => {
    if (listening) {
      stopListening();
    } else {
      startListening();
    }
  };

  useEffect(() => {
    return () => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    };
  }, []);

  if (!supported) {
    return (
      <Button
        type="button"
        size="icon"
        variant="ghost"
        disabled
        title="Voice input not supported in this browser"
        className="h-8 w-8 text-tertiary cursor-not-allowed"
      >
        <MicOff className="h-4 w-4" />
      </Button>
    );
  }

  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      onClick={toggleListening}
      disabled={disabled}
      title={listening ? "Click to stop speaking" : "Click to speak"}
      className={`h-8 w-8 rounded-lg flex items-center justify-center transition-all duration-200 active:scale-95 ${
        errorState
          ? "bg-red-500/10 text-red-500 hover:bg-red-500/15"
          : listening
            ? "bg-primary/10 text-primary hover:bg-primary/15 animate-voice-pulse"
            : "text-secondary hover:bg-surface-raised hover:text-primary"
      }`}
    >
      <Mic className="h-4 w-4" />
    </Button>
  );
}
