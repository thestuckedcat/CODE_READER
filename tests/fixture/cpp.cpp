int overload(int a) { return a; }
int overload(double a) { return (int)a; }
int cpp_entry() { return overload(1) + overload(2.0); }
struct Base { virtual int work(int x) { return x; } };
int dispatch(Base *b) { return b->work(1); }
struct DerivedA : Base { int work(int x) override { return x + 1; } };
struct DerivedB final : Base { int work(int x) override { return x + 2; } };
int qualified_dispatch(Base *b) { return b->Base::work(2); }
struct FinalWorker final { virtual int run(int x) { return x + 3; } };
int final_dispatch(FinalWorker *worker) { return worker->run(3); }
struct AbstractWorker { virtual int execute(int x) = 0; };
struct ConcreteWorker final : AbstractWorker { int execute(int x) override { return x + 4; } };
int abstract_dispatch(AbstractWorker *worker) { return worker->execute(4); }
