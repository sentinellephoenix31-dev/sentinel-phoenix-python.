import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class IncidentDialogue {
    private final LatestIncident latestIncident;
    private final LocalBrain localBrain = new LocalBrain();
    private final List<LocalBrain.Message> history = new ArrayList<>();

    private IncidentReasoning.Report currentIncident;

    public IncidentDialogue(java.nio.file.Path root) {
        latestIncident = new LatestIncident(root);
    }

    public Result begin(String question) throws IOException {
        currentIncident = null;
        history.clear();

        var report = latestIncident.loadReport();
        if (report.isEmpty()) {
            return new Result(
                    "I haven't recorded a honeypot connection yet.",
                    false,
                    "INCIDENT_REASONING"
            );
        }

        currentIncident = report.get();
        return explain(question);
    }

    public Result followUp(String question) {
        if (currentIncident == null) {
            return new Result(
                    "Choose an incident first. Ask me about the last incident.",
                    false,
                    "INCIDENT_REASONING"
            );
        }

        return explain(question);
    }

    public boolean hasIncident() {
        return currentIncident != null;
    }

    public void clear() {
        currentIncident = null;
        history.clear();
    }

    private Result explain(String question) {
        String deterministicAnswer = IncidentReasoning.answerIncidentQuestion(
                question, currentIncident
        );

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("source", "Sentinel Phoenix incident reasoning");
        context.put("deterministic_answer", deterministicAnswer);
        context.put("incident_report", currentIncident.toFullMap());
        context.put("explanation_scope", """
                Explain this selected incident using the supplied report.
                Keep the same incident for follow-up questions.

                Report timestamps may describe when the reasoning report was built.
                Do not present them as the connection time.

                The report's posture and policy action describe decisions.
                Use explicit decoy and sandbox state fields when explaining
                which measures are reported as active.

                Missing profile names, locations or other details are unknown.
                General attack explanations must be identified as general knowledge.
                A suspicious keyword is an indicator, not proof of exploitation.
                """);

        LocalBrain.Result generated = localBrain.chat(
                question, context, new ArrayList<>(history)
        );

        String response = generated.ok()
                ? generated.response()
                : deterministicAnswer;

        remember("user", question);
        remember("assistant", response);

        return new Result(
                response,
                generated.ok(),
                generated.ok()
                        ? LocalBrain.MODEL + "+SENTINEL_CONTEXT"
                        : "INCIDENT_REASONING"
        );
    }

    private void remember(String role, String content) {
        history.add(new LocalBrain.Message(role, content));
        while (history.size() > 4) {
            history.remove(0);
        }
    }

    public static void main(String[] args) throws IOException {
        IncidentDialogue dialogue = new IncidentDialogue(java.nio.file.Path.of("."));

        Result first = dialogue.begin("Why was the last incident dangerous?");
        System.out.println("SENTINEL > " + first.response());
        System.out.println("[SOURCE] " + first.source());

        if (dialogue.hasIncident()) {
            Result second = dialogue.followUp("Explain that more simply.");
            System.out.println("\nSENTINEL > " + second.response());
            System.out.println("[SOURCE] " + second.source());
        }
    }

    public record Result(String response, boolean llmUsed, String source) {
    }
}