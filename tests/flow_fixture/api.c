int twice(int value);
void consume(int value);

/* input is overwritten: it must not flow into the first consume call. */
int sdk_flow(int input, int flag) {
    int x = input;
    x = 0;
    consume(x);
    if (flag) {
        x = twice(input) + 3;
    } else {
        x = 7;
    }
    consume(x);
    return x;
}

/* These callsites must never share actual parameters. */
int isolated_calls(int input) {
    int ignored = twice(input);
    int answer = twice(7);
    return answer;
}
