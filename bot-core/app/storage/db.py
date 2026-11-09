import sqlite3
import threading

TABELAS = ["mentoria", "envio", "enquete_resposta", "kv", "alerta", "analise", "mensagem", "colaborador", "loja"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS loja(id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS colaborador(
  id INTEGER PRIMARY KEY, nome TEXT NOT NULL, telefone TEXT UNIQUE NOT NULL,
  loja_id INTEGER REFERENCES loja(id), papel TEXT NOT NULL DEFAULT 'COLABORADOR',
  data_entrada TEXT, gerente_id INTEGER REFERENCES colaborador(id),
  ativo INTEGER NOT NULL DEFAULT 1, consentimento_em TEXT, optout_em TEXT,
  resumo_contexto TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS mensagem(
  id INTEGER PRIMARY KEY, colaborador_id INTEGER NOT NULL REFERENCES colaborador(id),
  direcao TEXT NOT NULL, origem TEXT NOT NULL DEFAULT 'TEXTO', texto TEXT, transcricao TEXT,
  dia_jornada INTEGER, criada_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analise(
  id INTEGER PRIMARY KEY, mensagem_id INTEGER NOT NULL REFERENCES mensagem(id),
  intencao TEXT, categoria TEXT, sinal TEXT, gravidade TEXT, alvo TEXT, destinatario TEXT,
  confianca REAL, resposta TEXT, origem_analise TEXT, escalado_por_regra INTEGER);
CREATE TABLE IF NOT EXISTS alerta(
  id INTEGER PRIMARY KEY, colaborador_id INTEGER NOT NULL REFERENCES colaborador(id),
  analise_id INTEGER REFERENCES analise(id), destinatario_id INTEGER REFERENCES colaborador(id),
  canal TEXT NOT NULL, sinal TEXT, gravidade TEXT, sugestao TEXT, resumo TEXT,
  estado TEXT NOT NULL, criado_em TEXT NOT NULL, confirmado_em TEXT,
  lembrete_em TEXT, lembrado_em TEXT, retorno_em TEXT);
CREATE TABLE IF NOT EXISTS kv(chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS mentoria(
  id INTEGER PRIMARY KEY, mentor_id INTEGER NOT NULL REFERENCES colaborador(id),
  aprendiz_id INTEGER NOT NULL REFERENCES colaborador(id), inicio TEXT NOT NULL, fim TEXT);
CREATE TABLE IF NOT EXISTS envio(
  id INTEGER PRIMARY KEY, colaborador_id INTEGER NOT NULL REFERENCES colaborador(id),
  dia INTEGER NOT NULL, tipo TEXT NOT NULL, ref TEXT, enviado_em TEXT NOT NULL, concluido_em TEXT,
  UNIQUE(colaborador_id, dia));
CREATE TABLE IF NOT EXISTS enquete_resposta(
  id INTEGER PRIMARY KEY, enquete_id TEXT NOT NULL, colaborador_id INTEGER NOT NULL REFERENCES colaborador(id),
  opcao_id TEXT NOT NULL, rotulo TEXT, dia_jornada INTEGER, criada_em TEXT NOT NULL);
"""


class Banco:
    """SQLite com uma conexão compartilhada e um lock (a API roda em várias threads)."""

    def __init__(self, caminho: str = ":memory:"):
        self._lock = threading.RLock()
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.executescript(SCHEMA)

    def exec(self, sql, params=()):
        with self._lock:
            cur = self.con.execute(sql, params)
            self.con.commit()
            return cur

    def um(self, sql, params=()):
        with self._lock:
            return self.con.execute(sql, params).fetchone()

    def todos(self, sql, params=()):
        with self._lock:
            return self.con.execute(sql, params).fetchall()

    def resetar(self):
        with self._lock:
            self.con.execute("PRAGMA foreign_keys=OFF")
            for t in TABELAS:
                self.con.execute(f"DROP TABLE IF EXISTS {t}")
            self.con.executescript(SCHEMA)
            self.con.execute("PRAGMA foreign_keys=ON")
            self.con.commit()
