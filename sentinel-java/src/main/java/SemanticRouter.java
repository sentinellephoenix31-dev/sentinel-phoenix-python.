import java.text.Normalizer;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class SemanticRouter {

    public static final String VERSION = "2.1";

    private static final Set<String> FRENCH_WORDS = Set.of(
            "quoi", "que", "hier", "nuit", "aujourd", "semaine",
            "matin", "soir", "apres", "pendant", "depuis", "parti",
            "dormais", "absence", "attaque", "risque", "dangereux",
            "bizarre", "louche", "evenement", "resume", "passe"
    );

    private static final Pattern IPV4 =
            Pattern.compile("\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b");

    private static final Pattern ENGLISH_CLOCK = Pattern.compile(
            "\\bbetween\\s+(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?"
                    + "\\s+(?:and|to)\\s+(\\d{1,2})"
                    + "(?::(\\d{2}))?\\s*(am|pm)?\\b"
    );

    private static final Pattern FRENCH_CLOCK = Pattern.compile(
            "\\bentre\\s+(\\d{1,2})(?:h|:)(\\d{0,2})"
                    + "\\s+(?:et|a)\\s+(\\d{1,2})"
                    + "(?:h|:)(\\d{0,2})\\b"
    );

    private static final List<TimeRule> TIME_RULES = List.of(
            new TimeRule("ALL_TIME", List.of(
                    "all time", "entire history", "full history",
                    "since the beginning", "everything you know",
                    "tout l historique", "historique complet",
                    "depuis le debut")),

            new TimeRule("LAST_7_DAYS", List.of(
                    "last 7 days", "past 7 days", "previous 7 days",
                    "last seven days", "7 derniers jours",
                    "sept derniers jours")),

            new TimeRule("LAST_24_HOURS", List.of(
                    "last 24 hours", "past 24 hours",
                    "previous 24 hours", "24 dernieres heures",
                    "dernieres 24 heures")),

            new TimeRule("THIS_WEEK", List.of(
                    "this week", "current week", "cette semaine")),

            new TimeRule("THIS_WEEKEND", List.of(
                    "this weekend", "during the weekend",
                    "over the weekend", "ce week end",
                    "pendant le week end")),

            new TimeRule("LAST_NIGHT", List.of(
                    "last night", "overnight", "during the night",
                    "through the night", "while i slept",
                    "while i was asleep", "while i was sleeping",
                    "cette nuit", "hier soir", "pendant la nuit",
                    "durant la nuit", "pendant que je dormais",
                    "quand je dormais")),

            new TimeRule("YESTERDAY", List.of(
                    "yesterday", "previous day", "hier",
                    "journee d hier")),

            new TimeRule("THIS_MORNING", List.of(
                    "this morning", "ce matin")),

            new TimeRule("THIS_AFTERNOON", List.of(
                    "this afternoon", "cet apres midi")),

            new TimeRule("THIS_EVENING", List.of(
                    "this evening", "tonight", "ce soir")),

            new TimeRule("TODAY", List.of(
                    "today", "aujourd hui"))
    );

    private SemanticRouter() {
    }

    public static Route routeQuestion(String question) {
        String original = question == null ? "" : question.strip();
        String normalized = normalize(original);

        String language = detectLanguage(normalized);
        String sourceIp = extractIpv4(original);
        String presence = detectPresence(normalized);

        TimeRule matchedTime = null;

        for (TimeRule rule : TIME_RULES) {
            if (containsAny(normalized, rule.markers())) {
                matchedTime = rule;
                break;
            }
        }

        boolean explicitTime = matchedTime != null;
        String timeRange = explicitTime
                ? matchedTime.range() : "TODAY";

        if (presence != null && !explicitTime) {
            timeRange = "ALL_TIME";
        }

        Intent intent = detectIntent(normalized, sourceIp);

        return new Route(
                VERSION,
                original,
                language,
                intent.name(),
                intent.confidence(),
                timeRange,
                explicitTime,
                presence,
                sourceIp,
                detectClock(normalized)
        );
    }

    private static String normalize(String text) {
        return Normalizer.normalize(
                        text.toLowerCase(Locale.ROOT),
                        Normalizer.Form.NFKD)
                .replaceAll("\\p{M}+", "")
                .replaceAll("[^a-z0-9.:\\s]", " ")
                .replaceAll("\\s+", " ")
                .strip();
    }

    private static String detectLanguage(String text) {
        for (String word : text.split(" ")) {
            if (FRENCH_WORDS.contains(word)) {
                return "FR";
            }
        }

        return "EN";
    }

    private static String extractIpv4(String original) {
        Matcher match = IPV4.matcher(original);

        if (!match.find()) {
            return null;
        }

        String address = match.group();

        for (String part : address.split("\\.")) {
            if (Integer.parseInt(part) > 255) {
                return null;
            }
        }

        return address;
    }

    private static String detectPresence(String text) {
        if (containsAny(text, List.of(
                "while i was away", "while i was gone",
                "during my absence", "while i wasnt here",
                "while i wasn t here", "while i was not here",
                "pendant mon absence", "quand je n etais pas la",
                "pendant que j etais parti",
                "pendant que je n etais pas la"))) {

            return "OWNER_ABSENCE";
        }

        if (containsAny(text, List.of(
                "since i left", "after i left",
                "since i went out", "after i went out",
                "depuis que je suis parti",
                "apres que je sois parti",
                "apres mon depart", "depuis mon depart",
                "depuis que j ai quitte le bureau",
                "apres avoir quitte le bureau"))) {

            return "SINCE_OWNER_LEFT";
        }

        return null;
    }

    private static ClockWindow detectClock(String text) {
        Matcher english = ENGLISH_CLOCK.matcher(text);

        if (english.find()) {
            ClockWindow result = window(
                    toClock(
                            english.group(1),
                            english.group(2),
                            english.group(3)),
                    toClock(
                            english.group(4),
                            english.group(5),
                            english.group(6)));

            if (result != null) {
                return result;
            }
        }

        Matcher french = FRENCH_CLOCK.matcher(text);

        if (french.find()) {
            return window(
                    toClock(
                            french.group(1),
                            french.group(2),
                            null),
                    toClock(
                            french.group(3),
                            french.group(4),
                            null));
        }

        return null;
    }

    private static ClockWindow window(String start, String end) {
        return start == null || end == null
                ? null : new ClockWindow(start, end);
    }

    private static String toClock(
            String hours, String minutes, String meridiem) {

        int hour = Integer.parseInt(hours);
        int minute = minutes == null || minutes.isEmpty()
                ? 0 : Integer.parseInt(minutes);

        if (meridiem != null && (hour < 1 || hour > 12)) {
            return null;
        }

        if ("pm".equals(meridiem) && hour < 12) {
            hour += 12;

        } else if ("am".equals(meridiem) && hour == 12) {
            hour = 0;
        }

        if (hour > 23 || minute > 59) {
            return null;
        }

        return String.format(Locale.ROOT, "%02d:%02d", hour, minute);
    }

    private static Intent detectIntent(String text, String sourceIp) {
        if (containsAny(text, List.of(
                "exit", "quit", "bye", "goodbye",
                "close conversation", "end conversation",
                "stop conversation", "au revoir",
                "quitter", "ferme la conversation"))) {

            return new Intent("EXIT", 99);
        }

        if (containsAny(text, List.of(
                "help", "what can you do", "what can i ask",
                "show commands", "aide", "que peux tu faire",
                "que puis je demander", "montre les commandes"))) {

            return new Intent("HELP", 97);
        }

        if ("status".equals(text)
                || containsAny(text, List.of(
                "sentinel status", "system status",
                "how is sentinel", "is sentinel working",
                "is sentinel operational", "are you operational",
                "etat de sentinel", "statut de sentinel",
                "sentinel fonctionne", "sentinel est operationnel"))) {

            return new Intent("SYSTEM_STATUS", 96);
        }

        if (sourceIp != null) {
            return new Intent("SOURCE_LOOKUP", 96);
        }

        if (containsAny(text, List.of(
                "contain", "contained", "containment",
                "isolate", "isolated", "isolation",
                "quarantine", "confine", "confinement", "isole"))) {

            return new Intent("CONTAINMENT_SUMMARY", 91);
        }

        if (containsAny(text, List.of(
                "most dangerous", "worst incident", "worst event",
                "highest risk", "biggest threat", "nastiest",
                "most severe", "plus dangereux", "plus grave",
                "pire incident", "plus gros risque",
                "plus grosse menace"))) {

            return new Intent("MOST_DANGEROUS", 92);
        }

        if (containsAny(text, List.of(
                "what happened",
                "what happen",
                "what happens",
                "what is happening",
                "what s happening",
                "whats happening",
                "what was happening",
                "what has happened",
                "what s happened",
                "whats happened",
                "what went on",
                "what went down",
                "anything happen",
                "anything happened",
                "anything weird",
                "anything strange",
                "anything suspicious",
                "anything sketchy",
                "what did you detect",
                "what have you detected",
                "security recap",
                "security summary",
                "give me a recap",
                "qu est ce qui s est passe",
                "que s est il passe",
                "il s est passe quoi",
                "quelque chose de bizarre",
                "quelque chose de louche",
                "quelque chose de suspect",
                "tu as detecte quoi",
                "fais moi un resume",
                "resume des incidents"))) {

            return new Intent("INCIDENT_SUMMARY", 89);
        }

        return new Intent("GENERAL_MEMORY_QUERY", 55);
    }

    private static boolean containsAny(
            String text, List<String> markers) {

        String padded = " " + text.replace('.', ' ') + " ";

        for (String marker : markers) {
            if (padded.contains(" " + marker + " ")) {
                return true;
            }
        }

        return false;
    }

    public static void main(String[] args) {
        List<String> questions = args.length == 0
                ? List.of(
                        "What happened yesterday?",
                        "What's happening yesterday?",
                        "What happen today?",
                        "What has happened today?")
                : List.of(String.join(" ", args));

        for (String question : questions) {
            Route route = routeQuestion(question);

            System.out.println("Question: " + route.original());
            System.out.println("Intent: " + route.intent());
            System.out.println("Time range: " + route.timeRange());
            System.out.println();
        }
    }

    public record Route(
            String semanticVersion,
            String original,
            String language,
            String intent,
            int intentConfidence,
            String timeRange,
            boolean timeExplicit,
            String presenceContext,
            String sourceIp,
            ClockWindow explicitClock
    ) {
    }

    public record ClockWindow(String start, String end) {
    }

    private record TimeRule(String range, List<String> markers) {
    }

    private record Intent(String name, int confidence) {
    }
}