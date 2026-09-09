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

typedef struct AtlasMutex { int state; } AtlasMutex;
static AtlasMutex shared_gate = {0};
static int shared_counter = 0;
static void atlas_mutex_lock(AtlasMutex *mutex) { (void)mutex; }
static void atlas_mutex_unlock(AtlasMutex *mutex) { (void)mutex; }
void locked_write(int value) {
    atlas_mutex_lock(&shared_gate);
    shared_counter = value;
    atlas_mutex_unlock(&shared_gate);
}
int locked_read(void) {
    int value;
    atlas_mutex_lock(&shared_gate);
    value = shared_counter;
    atlas_mutex_unlock(&shared_gate);
    return value;
}
void unlocked_write(int value) { shared_counter = value; }
static void parameter_locked_write(AtlasMutex *mutex, int value) {
    atlas_mutex_lock(mutex);
    shared_counter = value;
    atlas_mutex_unlock(mutex);
}
void call_parameter_locked_write(int value) { parameter_locked_write(&shared_gate, value); }

struct SharedPair { int left; int right; };
static struct SharedPair shared_pair = {0, 0};
void alias_write(int value) {
    struct SharedPair *pointer = &shared_pair;
    struct SharedPair *copy = pointer;
    copy->left = value;
}
static void set_pair_left(struct SharedPair *pair, int value) { pair->left = value; }
void alias_argument_write(int value) { set_pair_left(&shared_pair, value); }
int direct_right_read(void) { return shared_pair.right; }
void install_callback(void) { register_callback(leaf); }
