import javafx.application.Application;

// Entry point for running JavaFX with classpath dependencies.
public final class GlobeLauncher {

    private GlobeLauncher() {
    }

    public static void main(String[] args) {
        Application.launch(IncidentGlobeFX.class, args);
    }
}