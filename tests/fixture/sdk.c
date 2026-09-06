#include "sdk.h"
static struct Config settings = {2, 0};
/// Multiply the request and send it to the leaf.
int sdk_entry(int input) {
    int adjusted = input * settings.scale;
    settings.scale = adjusted;
    return leaf(adjusted);
}
int callback_entry(int value) { return settings.submit(value); }
void register_callback(int (*callback)(int)) { settings.submit = callback; }
