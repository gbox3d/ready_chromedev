const cells = [...document.querySelectorAll('.cell')];
const board = document.querySelector('#board');
const turnIndicator = document.querySelector('#turn-indicator');
const turnMark = document.querySelector('.turn-mark');
const turnText = document.querySelector('#turn-text');
const resultBanner = document.querySelector('#result-banner');
const resetButton = document.querySelector('#reset-button');
const moveList = document.querySelector('#move-list');
const moveCount = document.querySelector('#move-count');
const roundBadge = document.querySelector('#round-badge');
const scores = { X: 0, O: 0, draw: 0 };
const winningLines = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];
const cellNames = ['Cell 1', 'Cell 2', 'Cell 3', 'Cell 4', 'Cell 5', 'Cell 6', 'Cell 7', 'Cell 8', 'Cell 9'];

let game = { board: Array(9).fill(''), current: 'X', moves: [], over: false };
let round = 1;

function getWinner() {
  return winningLines.find(([a, b, c]) => game.board[a] && game.board[a] === game.board[b] && game.board[a] === game.board[c]);
}

function playerName(mark) {
  return mark === 'X' ? 'Human' : 'AI';
}

function updateTurn() {
  const isX = game.current === 'X';
  turnMark.textContent = game.current;
  turnMark.className = `turn-mark ${isX ? 'x-mark' : 'o-mark'}`;
  turnText.textContent = playerName(game.current);
  turnIndicator.dataset.turn = game.current;
}

function renderHistory() {
  moveCount.textContent = `${game.moves.length} moves`;
  if (!game.moves.length) {
    moveList.innerHTML = '<li class="empty-log">Waiting for the first move.</li>';
    return;
  }
  moveList.innerHTML = game.moves.map((move, index) => `
    <li><span>${String(index + 1).padStart(2, '0')}</span><strong>${playerName(move.mark)}</strong><span>${cellNames[move.index]}</span></li>
  `).join('');
}

function renderBoard() {
  cells.forEach((cell, index) => {
    const mark = game.board[index];
    cell.textContent = mark;
    cell.className = `cell${mark ? ` ${mark.toLowerCase()}` : ''}`;
    cell.disabled = Boolean(mark) || game.over;
    cell.setAttribute('aria-label', `${cellNames[index]}, ${mark ? `${mark} (${playerName(mark)})` : 'empty'}`);
  });
  updateTurn();
  renderHistory();
}

function finishGame(winner) {
  game.over = true;
  if (winner) {
    scores[winner.mark] += 1;
    winner.line.forEach((index) => cells[index].classList.add('winner'));
    resultBanner.textContent = `${playerName(winner.mark)} wins!`;
    resultBanner.className = 'result-banner';
  } else {
    scores.draw += 1;
    resultBanner.textContent = 'Draw. No empty cells remain.';
    resultBanner.className = 'result-banner draw';
  }
  resultBanner.hidden = false;
  document.querySelector('#x-score').textContent = scores.X;
  document.querySelector('#o-score').textContent = scores.O;
  document.querySelector('#draw-score').textContent = scores.draw;
}

function play(index) {
  if (game.over || game.board[index]) return;
  const mark = game.current;
  game.board[index] = mark;
  game.moves.push({ mark, index });
  const line = winningLines.find(([a, b, c]) => game.board[a] && game.board[a] === game.board[b] && game.board[a] === game.board[c]);
  renderBoard();
  if (line) {
    finishGame({ mark, line });
    renderBoard();
    return;
  }
  if (game.board.every(Boolean)) {
    finishGame(null);
    renderBoard();
    return;
  }
  game.current = mark === 'X' ? 'O' : 'X';
  renderBoard();
}

function resetGame() {
  round += 1;
  game = { board: Array(9).fill(''), current: 'X', moves: [], over: false };
  roundBadge.textContent = `ROUND ${String(round).padStart(2, '0')}`;
  resultBanner.hidden = true;
  renderBoard();
}

board.addEventListener('click', (event) => {
  const cell = event.target.closest('.cell');
  if (cell) play(Number(cell.dataset.index));
});
resetButton.addEventListener('click', resetGame);
renderBoard();
