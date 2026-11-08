# Sentinel Phoenix — Java

Java version of the Sentinel Phoenix group project.
The original Python reference remains in ../sentinel-python.

## Features
- Honeypot event collection and risk analysis
- Local voice assistant and animated companion
- Camera and local face-profile features
- Incident replay, narration and ten animation categories

Animations illustrate recorded classifications or explicitly labelled demos.
They do not represent ten additional attack detectors or prove that traffic
was blocked.

## Requirements
- Windows x64 for the included native libraries
- Java 17 or newer and Maven
- Local Whisper, Vosk, Kokoro and Ollama services/models

Models, external tools, private profiles and runtime logs are excluded
from this repository. Voice features require these assets to be installed
separately using the paths configured in the Java sources and startup script.

## Build
Run from the sentinel-java directory:

    mvn compile

## Start
After installing the required local models and tools:

    .\launch-voice.cmd

For globe replay:

    .\launch-globe.cmd

## Collaboration
Develop changes on separate branches and submit pull requests.
Never commit credentials, face profiles or personal conversation logs.

## Status
The original developer reports successful operation on their Windows PC.
Installation on another computer still needs validation.
