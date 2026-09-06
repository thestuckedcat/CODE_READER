#include "sdk.h"
int leaf(int n) { return n + 1; }
int alternate(int value) { return leaf(value * 2); }
