"""Numerically checked shared LinUCB primitives; no IO or training side effects."""
from dataclasses import dataclass
import hashlib, json
import numpy as np

@dataclass(frozen=True)
class Score:
    exploit: float
    explore: float
    total: float

class SharedLinUCB:
    def __init__(self, dimension, ridge=1.0, alpha=0.5, A=None, b=None, max_condition=1e12):
        if not isinstance(dimension, int) or dimension < 1 or not np.isfinite(ridge) or ridge <= 0 or not np.isfinite(alpha) or alpha < 0:
            raise ValueError('invalid model parameters')
        self.dimension, self.ridge, self.alpha, self.max_condition = dimension, float(ridge), float(alpha), float(max_condition)
        self.A = np.eye(dimension, dtype=np.float64) * ridge if A is None else np.array(A, dtype=np.float64, copy=True)
        self.b = np.zeros(dimension, dtype=np.float64) if b is None else np.array(b, dtype=np.float64, copy=True)
        self._cached_digest = None
        self._cached_inverse = None
        self._cached_theta = None
        self._validate()

    def state_digest(self):
        header = json.dumps([self.dimension, self.ridge, self.alpha, self.max_condition], allow_nan=False).encode()
        return hashlib.sha256(header + self.A.tobytes() + self.b.tobytes()).hexdigest()

    def _validate(self):
        if self.A.shape != (self.dimension, self.dimension) or self.b.shape != (self.dimension,) or not np.isfinite(self.A).all() or not np.isfinite(self.b).all():
            raise ValueError('invalid state shape or nonfinite state')
        if not np.allclose(self.A, self.A.T, rtol=1e-10, atol=0.0):
            raise ValueError('asymmetric state')
        try:
            np.linalg.cholesky(self.A)
        except np.linalg.LinAlgError as exc:
            raise ValueError('state is not positive definite') from exc
        if not np.isfinite(self.max_condition) or self.max_condition <= 0 or np.linalg.cond(self.A) > self.max_condition:
            raise ValueError('ill-conditioned state')

    def _vector(self, x):
        x = np.asarray(x, dtype=np.float64)
        if x.shape != (self.dimension,) or not np.isfinite(x).all():
            raise ValueError('invalid feature vector')
        return x

    def _ensure_cached(self):
        """Validate the state and compute the inverse at most once per state.

        The digest guard is what keeps this safe: if ``A`` or ``b`` changes by any
        route -- ``observe``, ``revise`` or direct attribute mutation -- the digest
        no longer matches and the state is re-validated and re-inverted before it is
        used. Provenance (``state_digest``) is unchanged, so callers that compare
        digests before and after keep working.
        """
        digest = self.state_digest()
        if digest == self._cached_digest:
            return
        self._validate()
        inverse = np.linalg.solve(self.A, np.eye(self.dimension, dtype=np.float64))
        # A is symmetric positive definite (checked above), so A^-1 is too; the
        # symmetrisation only removes floating-point asymmetry.
        self._cached_inverse = 0.5 * (inverse + inverse.T)
        self._cached_theta = self._cached_inverse @ self.b
        self._cached_digest = digest

    def _score_cached(self, x):
        variance = float(x @ self._cached_inverse @ x)
        if not np.isfinite(variance) or variance < 0:
            raise ValueError('invalid uncertainty')
        exploit = float(self._cached_theta @ x)
        explore = float(self.alpha * np.sqrt(variance))
        if not np.isfinite(exploit + explore):
            raise ValueError('nonfinite score')
        return Score(exploit, explore, exploit + explore)

    def score(self, x):
        self._ensure_cached()
        return self._score_cached(self._vector(x))

    def score_many(self, features):
        """Score a batch of candidates after one validation.

        Same numbers as calling ``score`` in a loop, but the Cholesky check, the
        condition-number estimate and the matrix inverse happen once per batch
        instead of once per candidate.
        """
        if len(features) == 0:
            return []
        vectors = [self._vector(x) for x in features]
        self._ensure_cached()
        return [self._score_cached(x) for x in vectors]

    def observe(self, x, reward):
        x = self._vector(x)
        if not np.isfinite(reward) or not 0 <= reward <= 1:
            raise ValueError('invalid reward')
        candidate = SharedLinUCB(self.dimension, self.ridge, self.alpha, self.A + np.outer(x, x), self.b + reward*x, self.max_condition)
        self.A, self.b = candidate.A, candidate.b
        self.state_id = None

    def revise(self, x, old_reward, new_reward):
        x = self._vector(x)
        if any(not np.isfinite(r) or not 0 <= r <= 1 for r in (old_reward, new_reward)):
            raise ValueError('invalid reward')
        candidate = SharedLinUCB(self.dimension, self.ridge, self.alpha, self.A, self.b + (new_reward-old_reward)*x, self.max_condition)
        self.A, self.b = candidate.A, candidate.b
        self.state_id = None
