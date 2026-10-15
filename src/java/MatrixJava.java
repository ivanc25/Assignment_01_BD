import java.io.IOException;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Scanner;

public class MatrixJava {

    private static final double ABS_TOL = 1e-12;
    private static final double REL_TOL = 1e-12;

    // Store the dimension and flat matrix arrays together.
    private record Input(int n, double[] a, double[] b) {}
    private record Expected(int n, double[] values) {}

    private static int readDimension(Scanner scanner) {
        int n = scanner.nextInt();

        if (n <= 0) {
            throw new IllegalArgumentException(
                "Matrix size must be positive."
            );
        }

        return n;
    }

    private static double[] readArray(Scanner scanner, int length) {
        double[] values = new double[length];

        for (int i = 0; i < length; i++) {
            values[i] = scanner.nextDouble();

            if (!Double.isFinite(values[i])) {
                throw new IllegalArgumentException(
                    "Matrix values must be finite."
                );
            }
        }

        return values;
    }

    private static Input loadInput(Path path) throws IOException {
        try (Scanner scanner = new Scanner(path)) {
            // Read decimal points consistently on every system.
            scanner.useLocale(Locale.US);

            int n = readDimension(scanner);
            int elements = Math.multiplyExact(n, n);

            double[] a = readArray(scanner, elements);
            double[] b = readArray(scanner, elements);

            if (scanner.hasNext()) {
                throw new IllegalArgumentException(
                    "Unexpected extra input values."
                );
            }

            return new Input(n, a, b);
        }
    }

    private static Expected loadExpected(Path path) throws IOException {
        try (Scanner scanner = new Scanner(path)) {
            scanner.useLocale(Locale.US);

            int n = readDimension(scanner);
            int elements = Math.multiplyExact(n, n);
            double[] values = readArray(scanner, elements);

            if (scanner.hasNext()) {
                throw new IllegalArgumentException(
                    "Unexpected extra result values."
                );
            }

            return new Expected(n, values);
        }
    }

    public static void multiply(
        double[] a, double[] b, double[] c, int n
    ) {
        // Use the same i-j-k loop order as the Python implementation.
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double total = 0.0;

                for (int k = 0; k < n; k++) {
                    total += a[i * n + k] * b[k * n + j];
                }

                c[i * n + j] = total;
            }
        }
    }

    private static void checkResult(
        double[] actual, double[] expected
    ) {
        if (actual.length != expected.length) {
            throw new AssertionError("Result lengths differ.");
        }

        for (int i = 0; i < actual.length; i++) {
            double difference = Math.abs(actual[i] - expected[i]);
            double scale = Math.max(
                Math.abs(actual[i]), Math.abs(expected[i])
            );
            double tolerance = Math.max(ABS_TOL, REL_TOL * scale);

            if (!Double.isFinite(actual[i])
                || difference > tolerance) {
                throw new AssertionError(
                    "Mismatch at index " + i
                    + ": got " + actual[i]
                    + ", expected " + expected[i]
                );
            }
        }
    }

    private static void runTests(Path dataDir) throws IOException {
        String[] names = {"known", "identity", "zero", "fractional", "random16", "random32"};

        for (String name : names) {
            Input input = loadInput(
                dataDir.resolve("test_" + name + ".txt")
            );
            Expected expected = loadExpected(
                dataDir.resolve("test_" + name + "_expected.txt")
            );

            if (input.n() != expected.n()) {
                throw new AssertionError(
                    "Input and expected dimensions differ."
                );
            }

            // Allocate the output before calling the multiplication.
            double[] c = new double[input.a().length];

            multiply(input.a(), input.b(), c, input.n());
            checkResult(c, expected.values());

            System.out.println("PASS: " + name);
        }

        System.out.println("All correctness tests passed.");
    }

        // Make the computed result observable outside the multiplication.
    private static volatile double resultSink;

    private static double consumeResult(double[] values) {
        double checksum = 0.0;

        for (double value : values) {
            if (!Double.isFinite(value)) {
                throw new ArithmeticException("Non-finite result.");
            }
            checksum += value;
        }

        resultSink = checksum;
        return checksum;
    }

    private static double percentile(double[] sorted, double p) {
        // Linear interpolation, matching Python's inclusive quartiles.
        double position = (sorted.length - 1) * p;
        int lower = (int) Math.floor(position);
        int upper = (int) Math.ceil(position);

        return sorted[lower]
            + (sorted[upper] - sorted[lower]) * (position - lower);
    }

    private static void runBenchmark(
        Path inputPath, int warmups, int repetitions
    ) throws IOException {
        if (warmups < 1 || repetitions < 2) {
            throw new IllegalArgumentException(
                "Use at least one warm-up and two measured repetitions."
            );
        }

        // Loading and output allocation are outside the timed region.
        Input input = loadInput(inputPath);
        double[] c = new double[input.a().length];

        System.out.println(
            "Java " + System.getProperty("java.version")
            + " | n = " + input.n()
        );
        System.out.println("Warm-ups: " + warmups);
        System.out.println("Measured repetitions: " + repetitions);

        for (int i = 0; i < warmups; i++) {
            multiply(input.a(), input.b(), c, input.n());
            consumeResult(c);
        }

        long[] timesNs = new long[repetitions];
        double[] checksums = new double[repetitions];

        for (int i = 0; i < repetitions; i++) {
            long startNs = System.nanoTime();
            multiply(input.a(), input.b(), c, input.n());
            timesNs[i] = System.nanoTime() - startNs;

            // Consume the result after stopping the timer.
            checksums[i] = consumeResult(c);
        }

        Path resultsDir = Path.of("results");
        java.nio.file.Files.createDirectories(resultsDir);

        Path outputPath = resultsDir.resolve(
            "pilot_java_n" + input.n() + "_"
            + java.util.UUID.randomUUID() + ".csv"
        );

        try (java.io.BufferedWriter writer =
                 java.nio.file.Files.newBufferedWriter(
                     outputPath,
                     java.nio.charset.StandardCharsets.UTF_8,
                     java.nio.file.StandardOpenOption.CREATE_NEW,
                     java.nio.file.StandardOpenOption.WRITE
                 )) {
            writer.write(
                "phase,method,version,n,numeric_type,loop_order,"
                + "compute_threads,warmups,repetitions,repetition,"
                + "elapsed_ns,checksum\n"
            );

            for (int i = 0; i < repetitions; i++) {
                writer.write(String.format(
                    Locale.US,
                    "pilot,java,%s,%d,float64,ijk,1,%d,%d,%d,%d,%.17g%n",
                    System.getProperty("java.version"),
                    input.n(), warmups, repetitions, i + 1,
                    timesNs[i], checksums[i]
                ));
            }
        }

        double[] timesMs = new double[repetitions];

        for (int i = 0; i < repetitions; i++) {
            timesMs[i] = timesNs[i] / 1_000_000.0;
            System.out.printf(
                Locale.US,
                "Repetition %d: %.3f ms%n",
                i + 1, timesMs[i]
            );
        }

        java.util.Arrays.sort(timesMs);

        System.out.printf(
            Locale.US, "Median: %.3f ms%n",
            percentile(timesMs, 0.5)
        );
        System.out.printf(
            Locale.US, "IQR: %.3f ms%n",
            percentile(timesMs, 0.75) - percentile(timesMs, 0.25)
        );
        System.out.println(
                        "Results saved to: " + outputPath
        );
    }

    
    private static void streamBenchmark(String[] args) throws IOException {
        Input input = loadInput(Path.of(args[1]));
        int warmups = Integer.parseInt(args[2]);
        int repetitions = Integer.parseInt(args[3]);
        int batch = Integer.parseInt(args[4]);
        if (Math.min(warmups, Math.min(repetitions, batch)) < 1) {
            throw new IllegalArgumentException("Counts must be positive");
        }
        double[] c = new double[input.a().length];
        for (int i = 0; i < warmups; i++) {
            multiply(input.a(), input.b(), c, input.n());
            consumeResult(c);
        }
        for (int rep = 1; rep <= repetitions; rep++) {
            long elapsed = 0;
            double checksum = 0;
            for (int item = 0; item < batch; item++) {
                long start = System.nanoTime();
                multiply(input.a(), input.b(), c, input.n());
                elapsed += System.nanoTime() - start;
                checksum = consumeResult(c);
            }
            System.out.printf(Locale.US, "SAMPLE\t%d\t%d\t%d\t%.17g%n",
                rep, batch, elapsed, checksum);
            System.out.flush();
        }
        System.out.println("READY");
        System.out.flush();
        String reply = new java.io.BufferedReader(
            new java.io.InputStreamReader(System.in)).readLine();
        if (!"RELEASE".equals(reply)) {
            throw new IOException("Missing monitor acknowledgement");
        }
        java.lang.ref.Reference.reachabilityFence(input);
        java.lang.ref.Reference.reachabilityFence(c);
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 5 && args[0].equals("--stream")) {
            streamBenchmark(args);
            return;
        }

        if (args.length >= 1
            && args.length <= 2
            && args[0].equals("--test")) {

            Path dataDir = Path.of(args.length == 2 ? args[1] : "data");
            runTests(dataDir);

        } else if (args.length == 4 && args[0].equals("--benchmark")) {

            Path inputPath = Path.of(args[1]);
            int warmups = Integer.parseInt(args[2]);
            int repetitions = Integer.parseInt(args[3]);

            runBenchmark(inputPath, warmups, repetitions);

        } else {
            System.out.println(
                "Usage:\n"
                + "  java -cp src/java MatrixJava --test [data_directory]\n"
                + "  java -cp src/java MatrixJava --benchmark "
                + "<input_file> <warmups> <repetitions>"
            );
        }
    }
}