// Structured Clang CFG export. Python owns solving, caching and publication.
#include <clang/AST/RecursiveASTVisitor.h>
#include <clang/Basic/Version.h>
#include <clang/Analysis/CFG.h>
#include <clang/Frontend/FrontendActions.h>
#include <clang/Index/USRGeneration.h>
#include <clang/Lex/Lexer.h>
#include <clang/Tooling/Tooling.h>
#include <clang/Tooling/CompilationDatabase.h>
#include <llvm/Support/JSON.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/FileSystem.h>
#include <llvm/Support/Path.h>
#include <llvm/Support/raw_ostream.h>
#include <fstream>
#include <map>
using namespace clang;
using namespace clang::tooling;
using J = llvm::json::Object;
using A = llvm::json::Array;
static J Request;
static A Output;
static std::string usr(const Decl *d) {
  llvm::SmallString<128> s;
  if (d) index::generateUSRForDecl(d->getCanonicalDecl(), s);
  return std::string(s);
}
class Exporter : public RecursiveASTVisitor<Exporter> {
  ASTContext &ctx;
  SourceManager &sm;
  std::map<const Stmt *, std::string> ids;
  A nodes;
  std::string path(SourceLocation loc) {
    loc = sm.getExpansionLoc(loc);
    auto f = sm.getFilename(loc);
    llvm::SmallString<256> p(f);
    llvm::sys::fs::make_absolute(p);
    llvm::sys::path::remove_dots(p, true);
    return std::string(p);
  }
  unsigned offset(SourceLocation loc) { return sm.getFileOffset(sm.getExpansionLoc(loc)); }
  J location(SourceRange r) {
    auto end = Lexer::getLocForEndOfToken(sm.getExpansionLoc(r.getEnd()), 0, sm, ctx.getLangOpts());
    return J{{"file", path(r.getBegin())}, {"start", offset(r.getBegin())},
             {"end", end.isValid() ? offset(end) : offset(r.getEnd())},
             {"line", sm.getExpansionLineNumber(r.getBegin())},
             {"column", sm.getExpansionColumnNumber(r.getBegin())}};
  }
  std::string text(SourceRange r) {
    return Lexer::getSourceText(CharSourceRange::getTokenRange(r), sm, ctx.getLangOpts()).str();
  }
  J variable(const ValueDecl *d) {
    auto v = dyn_cast<VarDecl>(d);
    return J{{"usr", usr(d)}, {"name", d->getNameAsString()}, {"type", d->getType().getAsString()},
      {"scalar", d->getType()->isArithmeticType() || d->getType()->isEnumeralType()},
      {"volatile", d->getType().isVolatileQualified()},
      {"local", bool(v && v->hasLocalStorage())}, {"function", isa<FunctionDecl>(d)}};
  }
  std::string node(const Stmt *s) {
    if (!s) return "";
    if (ids.count(s)) return ids[s];
    auto id = "n" + std::to_string(ids.size()); ids[s] = id;
    J o{{"id", id}, {"kind", s->getStmtClassName()}, {"location", location(s->getSourceRange())},
        {"text", text(s->getSourceRange())}};
    if (auto e = dyn_cast<Expr>(s)) {
      o["type"] = e->getType().getAsString();
      o["scalar"] = e->getType()->isArithmeticType() || e->getType()->isEnumeralType();
    }
    A children;
    for (auto c : s->children()) if (c) children.push_back(node(c));
    o["children"] = std::move(children);
    if (auto r = dyn_cast<DeclRefExpr>(s)) o["variable"] = variable(r->getDecl());
    if (auto b = dyn_cast<BinaryOperator>(s)) o["operator"] = b->getOpcodeStr().str();
    if (auto u = dyn_cast<UnaryOperator>(s)) {
      o["operator"] = UnaryOperator::getOpcodeStr(u->getOpcode()).str();
      o["postfix"] = u->isPostfix();
    }
    if (auto c = dyn_cast<CastExpr>(s)) o["cast"] = c->getCastKindName();
    if (auto c = dyn_cast<CallExpr>(s)) {
      A args; for (auto a : c->arguments()) args.push_back(node(a));
      o["arguments"] = std::move(args);
      o["target_usr"] = usr(c->getDirectCallee());
      o["virtual"] = bool(c->getDirectCallee() && isa<CXXMethodDecl>(c->getDirectCallee()) && cast<CXXMethodDecl>(c->getDirectCallee())->isVirtual());
    }
    if (auto d = dyn_cast<DeclStmt>(s)) {
      A decls;
      for (auto decl : d->decls()) if (auto v = dyn_cast<VarDecl>(decl)) {
        J row = variable(v); row["initializer"] = node(v->getInit()); decls.push_back(std::move(row));
      }
      o["declarations"] = std::move(decls);
    }
    nodes.push_back(std::move(o)); return id;
  }
public:
  Exporter(ASTContext &c) : ctx(c), sm(c.getSourceManager()) {}
  bool VisitFunctionDecl(FunctionDecl *f) {
    if (!f->isThisDeclarationADefinition() || !f->hasBody()) return true;
    if (sm.isInSystemHeader(f->getLocation())) return true;
    std::string fid;
    for (auto &v : *Request.getArray("functions")) {
      auto *o=v.getAsObject();
      if (o->getString("file")==path(f->getBeginLoc()) && o->getInteger("start")==offset(f->getBeginLoc()))
        fid=o->getString("id")->str();
    }
    if (fid.empty()) return true;
    ids.clear();nodes.clear();
    CFG::BuildOptions opts; opts.setAllAlwaysAdd(); opts.AddEHEdges=true;
    opts.AddImplicitDtors=true; opts.AddTemporaryDtors=true;
    auto cfg=CFG::buildCFG(f,f->getBody(),&ctx,opts);
    J out{{"id",fid},{"usr",usr(f)},{"format","clang_cfg_v1"}};
    if (!cfg) {out["status"]="unsupported";Output.push_back(std::move(out));return true;}
    A blocks;
    for (auto *b : *cfg) {
      A operations,successors,extra;
      for (auto &elem : *b) {
        if (auto s=elem.getAs<CFGStmt>()) operations.push_back(node(s->getStmt()));
        else extra.push_back(int(elem.getKind()));
      }
      int ordinal=0;
      for (auto i=b->succ_begin();i!=b->succ_end();++i,++ordinal) {
        auto *dest=i->getReachableBlock();
        J edge{{"ordinal",ordinal},{"reachable",bool(dest)}};
        if (dest) {edge["target"]=int(dest->getBlockID());
          if (auto l=dest->getLabel()) edge["label"]=text(l->getSourceRange());}
        successors.push_back(std::move(edge));
      }
      auto *term=b->getTerminatorStmt();
      J row{{"id",int(b->getBlockID())},{"operations",std::move(operations)},
        {"successors",std::move(successors)},{"opaque_elements",std::move(extra)},
        {"terminator",term?term->getStmtClassName():""},
        {"condition",node(b->getTerminatorCondition())},
        {"condition_text",b->getTerminatorCondition()?text(b->getTerminatorCondition()->getSourceRange()):""}};
      blocks.push_back(std::move(row));
    }
    A params;for (auto p:f->parameters())params.push_back(variable(p));
    out["parameters"]=std::move(params);out["nodes"]=std::move(nodes);out["blocks"]=std::move(blocks);
    out["entry"]=int(cfg->getEntry().getBlockID());out["exit"]=int(cfg->getExit().getBlockID());
    out["status"]="ready";Output.push_back(std::move(out));return true;
  }
};
class Consumer : public ASTConsumer { void HandleTranslationUnit(ASTContext &c) override { Exporter(c).TraverseDecl(c.getTranslationUnitDecl()); } };
class Action : public ASTFrontendAction { std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &,llvm::StringRef) override {return std::make_unique<Consumer>();} };
int main(int argc,char **argv) {
  if (argc==2 && std::string(argv[1])=="--version") {llvm::outs()<<"atlas-semantic 1 clang "<<CLANG_VERSION_STRING<<"\n";return 0;}
  if(argc!=3){llvm::errs()<<"Usage: atlas-semantic request.json output.json\n";return 2;}
  auto buf=llvm::MemoryBuffer::getFile(argv[1]);if(!buf)return 2;
  auto parsed=llvm::json::parse((*buf)->getBuffer());if(!parsed || !parsed->getAsObject())return 2;
  Request=std::move(*parsed->getAsObject());
  std::vector<std::string> args;for(auto &v:*Request.getArray("arguments"))args.push_back(v.getAsString()->str());
  FixedCompilationDatabase db(Request.getString("directory")->str(),args);
  ClangTool tool(db,{Request.getString("file")->str()});
  int code=tool.run(newFrontendActionFactory<Action>().get());
  if(code)return code;
  std::error_code ec;llvm::raw_fd_ostream os(argv[2],ec);if(ec)return 2;
  os<<llvm::json::Value(J{{"protocol",1},{"clang_version",CLANG_VERSION_STRING},{"functions",std::move(Output)}});return 0;
}
