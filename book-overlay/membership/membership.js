import { firebaseConfig } from './config.js';

const status = document.querySelector('#status');
const visitor = document.querySelector('#visitor');
const reader = document.querySelector('#reader');
const join = document.querySelector('#join');
const logout = document.querySelector('#sign-out');
const remove = document.querySelector('#remove');
const identity = document.querySelector('#identity');
const removeBox = document.querySelector('#remove-box');
let current = null;

function message(error) {
  switch (error?.code) {
    case 'auth/popup-closed-by-user': return 'Sign-in cancelled. You can try again when you’re ready.';
    case 'auth/popup-blocked': return 'Your browser blocked the Google window. Allow pop-ups for this page and try again.';
    case 'auth/network-request-failed': return 'Couldn’t connect to Google. Check your connection and try again.';
    case 'auth/unauthorized-domain':
    case 'auth/operation-not-allowed': return 'Registration is not available at this address yet. You can still use the textbook.';
    default: return 'Couldn’t complete that action. Please try again.';
  }
}

async function initialise() {
  if (!firebaseConfig) {
    status.textContent = 'Free registration is not open yet. You can use the textbook without an account.';
    return;
  }
  try {
    const sdk = 'https://www.gstatic.com/firebasejs/13.3.0/';
    const [{ initializeApp }, authSdk] = await Promise.all([
      import(sdk + 'firebase-app.js'), import(sdk + 'firebase-auth.js')
    ]);
    const {
      getAuth, browserLocalPersistence, setPersistence, GoogleAuthProvider,
      onAuthStateChanged, signInWithPopup, signOut, deleteUser, reauthenticateWithPopup
    } = authSdk;
    const auth = getAuth(initializeApp(firebaseConfig));
    await setPersistence(auth, browserLocalPersistence);
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    onAuthStateChanged(auth, (user) => {
      current = user;
      visitor.hidden = Boolean(user);
      reader.hidden = !user;
      removeBox.open = false;
      identity.textContent = user?.email ? 'Signed in as ' + user.email : '';
      status.textContent = user ? 'Your free membership is active.' : 'Sign in to create or open your free account.';
    }, () => { status.textContent = 'Couldn’t check your account. Please reload the page.'; });

    function bind(button, pending, task) {
      button.addEventListener('click', async () => {
        if (join.disabled || logout.disabled || remove.disabled) return;
        button.disabled = true;
        status.textContent = pending;
        try { await task(); }
        catch (error) { status.textContent = message(error); }
        finally { button.disabled = false; }
      });
    }
    bind(join, 'Opening Google sign-in…', async () => { await signInWithPopup(auth, provider); });
    bind(logout, 'Signing out…', async () => { await signOut(auth); });
    bind(remove, 'Removing your membership…', async () => {
      const user = current;
      if (!user) return;
      try { await deleteUser(user); }
      catch (error) {
        if (error?.code !== 'auth/requires-recent-login') throw error;
        status.textContent = 'Confirm your Google account to delete this membership.';
        await reauthenticateWithPopup(user, provider);
        await deleteUser(user);
      }
    });
  } catch {
    status.textContent = 'Registration couldn’t load. You can still use the textbook.';
  }
}

void initialise();
