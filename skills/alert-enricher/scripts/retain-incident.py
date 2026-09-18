#!/usr/bin/env python3
import sys
import json
import os
from hermes_tools import hindsight_retain

def retain_incident():
    # Simplistic script to demonstrate the pattern.
    # In production, this would grab context from the thread history.
    if len(sys.argv) < 2:
        print("Usage: retain-incident <solucao_breve>")
        return

    solucao = " ".join(sys.argv[1:])
    context = "incident_resolution"
    
    # Stores the core fact for long-term memory
    result = hindsight_retain(
        content=f"Solução para incidentes recorrentes: {solucao}",
        context=context,
        tags=["auto-incident-resolution", "infra-ops"]
    )
    
    print(f"Aprendizado armazenado com sucesso: {solucao}")

if __name__ == "__main__":
    retain_incident()
