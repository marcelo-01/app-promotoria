/**
 * Coletar o vencimento deste produto? — a conta, no aparelho.
 *
 * Esta é a metade de campo da conta que começa em `app/merchandising/expiry.py`.
 * O servidor manda os ingredientes na folha de contagem (o estoque do último dia
 * completo, o que as planilhas do ERP registraram desde então, o vencido já
 * retirado, a validade na chegada); aqui eles se fecham com o número que o
 * promotor acabou de contar.
 *
 * POR QUE A CONTA É DAQUI
 * -----------------------
 * Porque a ponta de cima do ciclo é a contagem de AGORA. O que precisa caber
 * dentro de uma validade é o estoque que está na loja com o promotor na frente
 * dele, não o da visita passada — e esse número não existe no servidor no
 * momento em que a folha é montada: ele está sendo digitado. Fechar a conta aqui
 * também é o que permite o bloqueio acontecer sem rede, que é a regra da tela de
 * contagem.
 *
 * A CONTA
 * -------
 *     ciclo         = dias entre o último dia completo e hoje
 *     venda         = estoque anterior + faturado + brinde − estoque de hoje − vencidos
 *     dias a escoar = (estoque de hoje ÷ venda) × ciclo
 *     COLETA se dias a escoar > validade na chegada
 *
 * Ou seja: se o estoque de hoje, no ritmo de hoje, leva mais tempo para sair do
 * que a mercadoria tem de vida ao chegar, ela vai vencer na prateleira.
 *
 * O QUE ELA NÃO FAZ
 * -----------------
 * Ela **não sabe a idade do que está na loja**. Pergunta "esse estoque cabe numa
 * validade?", não "essas unidades específicas são velhas?". Duas consequências
 * que não são defeito e sim desenho: ela avisa cedo e não alivia enquanto a
 * cobertura for alta; e ela para de avisar se a venda acelerar, mesmo que ainda
 * haja mercadoria velha na loja.
 *
 * A data impressa na embalagem continua sendo a única verdade de campo, e só o
 * promotor a enxerga. Esta conta escolhe A QUEM PERGUNTAR; não substitui a
 * pergunta.
 */

// Diferença de quantidade abaixo disto é ruído de arredondamento, não venda nem
// entrega. É o mesmo EPS do `expiry.py`.
const EPS = 0.001

const numero = (valor) => (valor == null ? 0 : Number(valor) || 0)

/**
 * Dias entre dois dias locais em 'AAAA-MM-DD'.
 *
 * Construídos campo a campo, e não por `new Date('2026-09-10')`, que seria lido
 * como UTC e daria um dia a menos em quem está a oeste de Greenwich.
 */
export function diasEntre(de, ate) {
  if (!de || !ate) return 0
  const [a1, m1, d1] = de.split('-').map(Number)
  const [a2, m2, d2] = ate.split('-').map(Number)
  const inicio = new Date(a1, m1 - 1, d1)
  const fim = new Date(a2, m2 - 1, d2)
  return Math.round((fim - inicio) / 86400000)
}

/**
 * O veredito de um produto, com a conta aberta — ou `null` quando não há coleta
 * a pedir.
 *
 * Devolve `null` também quando não há o que julgar, e os casos são diferentes
 * entre si de propósito:
 *
 * * sem validade na chegada cadastrada — o produto não entra nesta conta;
 * * sem estoque anterior — produto que nunca foi contado neste cliente não tem
 *   ponto de partida, e um ciclo precisa de duas pontas;
 * * ciclo de zero dia ou menos — não existe intervalo para dividir;
 * * estoque de hoje zerado — não há mercadoria para vencer nem data para ler.
 */
export function veredito({
  shelfLife, previousStock, invoiced, gifted, removed, currentStock, cycleDays,
}) {
  const vida = numero(shelfLife)
  if (!vida) return null
  if (previousStock == null) return null
  if (!(cycleDays > 0)) return null

  const estoque = numero(currentStock)
  if (estoque <= EPS) return null

  // A venda é o que sobra depois de descontar o que se sabe que entrou e o que
  // se sabe que foi para o lixo. Negativa não existe: entrou mercadoria que as
  // planilhas não cobriram, e isso não é venda ao contrário.
  const venda = Math.max(
    0,
    numero(previousStock) + numero(invoiced) + numero(gifted) - estoque - numero(removed),
  )

  // Não girou nada no ciclo. Estoque parado não sai sozinho — vence.
  if (venda <= EPS) {
    return {
      reason: 'parado',
      daysToClear: null,
      sold: 0,
      cycleDays,
      shelfLife: vida,
    }
  }

  const dias = (estoque / venda) * cycleDays
  if (dias <= vida) return null

  return {
    reason: 'nao_escoa',
    daysToClear: Math.round(dias * 10) / 10,
    sold: Math.round(venda * 1000) / 1000,
    cycleDays,
    shelfLife: vida,
  }
}
