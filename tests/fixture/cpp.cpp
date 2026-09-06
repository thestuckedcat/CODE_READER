int overload(int a) { return a; }
int overload(double a) { return (int)a; }
int cpp_entry() { return overload(1) + overload(2.0); }
struct Base { virtual int work(int x) { return x; } };
int dispatch(Base *b) { return b->work(1); }
