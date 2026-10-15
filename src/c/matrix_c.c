#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#include <float.h>
#include <windows.h>

#define ABS_TOL 1e-12
#define REL_TOL 1e-12

_Static_assert(
    sizeof(double) == 8 && DBL_MANT_DIG == 53 && DBL_MAX_EXP == 1024,
    "This implementation requires binary64 doubles."
);

typedef struct {
    size_t n;
    double *a;
    double *b;
} Input;

typedef struct {
    size_t n;
    double *values;
} Expected;


static void fail(const char *message) {
    fprintf(stderr, "ERROR: %s\n", message);
    exit(EXIT_FAILURE);
}


static FILE *open_file(const char *path) {
    FILE *file = fopen(path, "r");

    if (file == NULL) {
        fprintf(stderr, "ERROR: Cannot open %s\n", path);
        exit(EXIT_FAILURE);
    }

    return file;
}


static size_t read_dimension(FILE *file) {
    int dimension;

    if (fscanf(file, "%d", &dimension) != 1 || dimension <= 0) {
        fail("Invalid matrix dimension.");
    }

    size_t n = (size_t) dimension;

    // Check both the element count and the allocation size.
    if (n > SIZE_MAX / n) {
        fail("Matrix dimension is too large.");
    }

    if (n * n > SIZE_MAX / sizeof(double)) {
        fail("Matrix allocation size is too large.");
    }

    return n;
}


static double *allocate_array(size_t length) {
    double *values = malloc(length * sizeof(double));

    if (values == NULL) {
        fail("Memory allocation failed.");
    }

    return values;
}


static double *read_array(FILE *file, size_t length) {
    double *values = allocate_array(length);

    for (size_t i = 0; i < length; i++) {
        if (fscanf(file, "%lf", &values[i]) != 1) {
            fail("Missing or invalid matrix value.");
        }

        if (!isfinite(values[i])) {
            fail("Matrix values must be finite.");
        }
    }

    return values;
}


static void check_file_end(FILE *file) {
    char extra;

    // The leading space skips trailing whitespace.
    if (fscanf(file, " %c", &extra) == 1) {
        fail("Unexpected extra values in file.");
    }

    if (ferror(file)) {
        fail("Error while reading file.");
    }
}


static Input load_input(const char *path) {
    FILE *file = open_file(path);

    Input input;
    input.n = read_dimension(file);

    size_t elements = input.n * input.n;
    input.a = read_array(file, elements);
    input.b = read_array(file, elements);

    check_file_end(file);
    fclose(file);

    return input;
}


static Expected load_expected(const char *path) {
    FILE *file = open_file(path);

    Expected expected;
    expected.n = read_dimension(file);
    expected.values = read_array(file, expected.n * expected.n);

    check_file_end(file);
    fclose(file);

    return expected;
}


void multiply(
    const double *a,
    const double *b,
    double *c,
    size_t n
) {
    // Use the same i-j-k loop order as Python and Java.
    for (size_t i = 0; i < n; i++) {
        for (size_t j = 0; j < n; j++) {
            double total = 0.0;

            for (size_t k = 0; k < n; k++) {
                total += a[i * n + k] * b[k * n + j];
            }

            c[i * n + j] = total;
        }
    }
}


static void check_result(
    const double *actual,
    const double *expected,
    size_t length
) {
    for (size_t i = 0; i < length; i++) {
        double difference = fabs(actual[i] - expected[i]);
        double scale = fmax(fabs(actual[i]), fabs(expected[i]));
        double tolerance = fmax(ABS_TOL, REL_TOL * scale);

        if (!isfinite(actual[i]) || difference > tolerance) {
            fprintf(
                stderr,
                "ERROR: Mismatch at index %zu: "
                "got %.17g, expected %.17g\n",
                i, actual[i], expected[i]
            );
            exit(EXIT_FAILURE);
        }
    }
}


static void build_path(
    char *buffer,
    size_t capacity,
    const char *directory,
    const char *name,
    const char *suffix
) {
    int written = snprintf(
        buffer, capacity, "%s/test_%s%s.txt",
        directory, name, suffix
    );

    if (written < 0 || (size_t) written >= capacity) {
        fail("File path is too long.");
    }
}


static void run_tests(const char *data_dir) {
    const char *names[] = {
        "known", "identity", "zero", "fractional", "random16", "random32"
    };
    size_t test_count = sizeof(names) / sizeof(names[0]);

    for (size_t t = 0; t < test_count; t++) {
        char input_path[1024];
        char expected_path[1024];

        build_path(
            input_path, sizeof(input_path),
            data_dir, names[t], ""
        );
        build_path(
            expected_path, sizeof(expected_path),
            data_dir, names[t], "_expected"
        );

        Input input = load_input(input_path);
        Expected expected = load_expected(expected_path);

        if (input.n != expected.n) {
            fail("Input and expected dimensions differ.");
        }

        size_t elements = input.n * input.n;

        // Every output element is overwritten by multiply.
        double *c = allocate_array(elements);

        multiply(input.a, input.b, c, input.n);
        check_result(c, expected.values, elements);

        printf("PASS: %s\n", names[t]);

        // Release the dynamically allocated memory.
        free(input.a);
        free(input.b);
        free(c);
        free(expected.values);
    }

    printf("All correctness tests passed.\n");
}

static volatile double result_sink;


static double consume_result(const double *values, size_t length) {
    double checksum = 0.0;

    for (size_t i = 0; i < length; i++) {
        if (!isfinite(values[i])) {
            fail("Non-finite result.");
        }
        checksum += values[i];
    }

    result_sink = checksum;
    return checksum;
}


static int compare_doubles(const void *left, const void *right) {
    double a = *(const double *) left;
    double b = *(const double *) right;

    return (a > b) - (a < b);
}


static double percentile(
    const double *sorted, size_t length, double p
) {
    double position = (length - 1) * p;
    size_t lower = (size_t) floor(position);
    size_t upper = (size_t) ceil(position);

    return sorted[lower]
        + (sorted[upper] - sorted[lower]) * (position - lower);
}


static void run_benchmark(
    const char *input_path,
    const char *output_path
) {
    // Fixed settings for this first pilot.
    const int warmups = 3;
    const int repetitions = 5;

    Input input = load_input(input_path);
    size_t elements = input.n * input.n;
    double *c = allocate_array(elements);

    LARGE_INTEGER frequency;
    if (!QueryPerformanceFrequency(&frequency)
        || frequency.QuadPart <= 0) {
        fail("Cannot initialise the performance counter.");
    }

    // Exclusive creation prevents overwriting an earlier run.
    FILE *output = fopen(output_path, "wx");
    if (output == NULL) {
        fail("Cannot create CSV: check the folder and use a new filename.");
    }

    printf("C | n = %zu\n", input.n);
    printf("Warm-ups: %d\n", warmups);
    printf("Measured repetitions: %d\n", repetitions);

    for (int i = 0; i < warmups; i++) {
        multiply(input.a, input.b, c, input.n);
        consume_result(c, elements);
    }

    double times_ns[5];
    double checksums[5];

    for (int i = 0; i < repetitions; i++) {
        LARGE_INTEGER start;
        LARGE_INTEGER end;

        if (!QueryPerformanceCounter(&start)) {
            fail("Cannot read the performance counter.");
        }

        multiply(input.a, input.b, c, input.n);

        if (!QueryPerformanceCounter(&end)) {
            fail("Cannot read the performance counter.");
        }

        times_ns[i] =
            (double) (end.QuadPart - start.QuadPart)
            * 1e9 / (double) frequency.QuadPart;

        // Read the result outside the timed region.
        checksums[i] = consume_result(c, elements);
    }

    fprintf(
        output,
        "phase,method,n,numeric_type,loop_order,compute_threads,"
        "warmups,repetitions,repetition,elapsed_ns,checksum\n"
    );

    double times_ms[5];

    for (int i = 0; i < repetitions; i++) {
        fprintf(
            output,
            "pilot,c,%zu,float64,ijk,1,%d,%d,%d,%.3f,%.17g\n",
            input.n, warmups, repetitions, i + 1,
            times_ns[i], checksums[i]
        );

        times_ms[i] = times_ns[i] / 1e6;
        printf("Repetition %d: %.3f ms\n", i + 1, times_ms[i]);
    }

    int write_failed = ferror(output);
    int close_status = fclose(output);

    if (write_failed || close_status != 0) {
        fail("Could not save all CSV results.");
    }

    qsort(
        times_ms, (size_t) repetitions,
        sizeof(double), compare_doubles
    );

    printf(
        "Median: %.3f ms\n",
        percentile(times_ms, (size_t) repetitions, 0.5)
    );
    printf(
        "IQR: %.3f ms\n",
        percentile(times_ms, (size_t) repetitions, 0.75)
        - percentile(times_ms, (size_t) repetitions, 0.25)
    );
    printf("Results saved to: %s\n", output_path);

    free(input.a);
    free(input.b);
    free(c);
}


static void stream_benchmark(char *argv[]) {
    int warmups = atoi(argv[3]);
    int repetitions = atoi(argv[4]);
    int batch = atoi(argv[5]);
    if (warmups < 1 || repetitions < 1 || batch < 1) {
        fail("Counts must be positive.");
    }
    Input input = load_input(argv[2]);
    size_t elements = input.n * input.n;
    double *c = allocate_array(elements);
    LARGE_INTEGER frequency;
    if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0) {
        fail("Cannot initialise timer.");
    }
    for (int i = 0; i < warmups; i++) {
        multiply(input.a, input.b, c, input.n);
        consume_result(c, elements);
    }
    for (int rep = 1; rep <= repetitions; rep++) {
        double elapsed = 0.0;
        double checksum = 0.0;
        for (int item = 0; item < batch; item++) {
            LARGE_INTEGER start, end;
            if (!QueryPerformanceCounter(&start)) fail("Timer failure.");
            multiply(input.a, input.b, c, input.n);
            if (!QueryPerformanceCounter(&end)) fail("Timer failure.");
            elapsed += (double)(end.QuadPart - start.QuadPart)
                * 1e9 / (double)frequency.QuadPart;
            checksum = consume_result(c, elements);
        }
        printf("SAMPLE\t%d\t%d\t%.3f\t%.17g\n",
            rep, batch, elapsed, checksum);
        fflush(stdout);
    }
    puts("READY");
    fflush(stdout);
    char reply[32];
    if (fgets(reply, sizeof(reply), stdin) == NULL
        || strncmp(reply, "RELEASE", 7) != 0) {
        fail("Missing monitor acknowledgement.");
    }
    free(input.a); free(input.b); free(c);
}

int main(int argc, char *argv[]) {
    if (argc == 6 && strcmp(argv[1], "--stream") == 0) {
        stream_benchmark(argv);
        return EXIT_SUCCESS;
    }

    if ((argc == 2 || argc == 3)
        && strcmp(argv[1], "--test") == 0) {

        const char *data_dir = argc == 3 ? argv[2] : "data";
        run_tests(data_dir);
        return EXIT_SUCCESS;
    }

    if (argc == 4 && strcmp(argv[1], "--benchmark") == 0) {
        run_benchmark(argv[2], argv[3]);
        return EXIT_SUCCESS;
    }

    printf(
        "Usage:\n"
        "  matrix_c.exe --test [data_directory]\n"
        "  matrix_c.exe --benchmark <input_file> <output_csv>\n"
    );

    return EXIT_FAILURE;
}