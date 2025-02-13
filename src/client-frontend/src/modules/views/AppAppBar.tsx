import React from 'react';
import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import AppBar from '../components/AppBar';
import Toolbar from '../components/Toolbar';
import { useMediaQuery } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import IconButton from '@mui/material/IconButton';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { selectIsLoggedIn, selectLanguage } from '../ducks/userSlice';
import { useNavigate } from 'react-router-dom';

const rightLink = {
  fontSize: 16,
  color: 'common.white',
  ml: 3,
};

function AppAppBar() {
  const isSmallScreen = useMediaQuery('(max-width: 800px)');
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const isLoggedIn = useSelector((state: RootState) => selectIsLoggedIn(state));
  const language = useSelector(selectLanguage);
  const navigate = useNavigate()


  const toggleDrawer = (open: boolean) => () => {
    setDrawerOpen(open);
  };

  return (
    <div>
      <AppBar position="fixed">
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          {/* Left Side */}
          <Box sx={{ flex: 1 }}>
            {isSmallScreen && (
              <IconButton
                edge="start"
                color="inherit"
                aria-label="menu"
                onClick={toggleDrawer(true)}
              >
                <MenuIcon />
              </IconButton>
            )}
          </Box>

          {/* Center Logo */}
          <Link
            variant="h6"
            underline="none"
            color="inherit"
            sx={{ fontSize: 24 }}
            href="/"
          >
            {isSmallScreen ? `RCW ${import.meta.env.VITE_CHURCH_CITY}` : `Restored Church ${import.meta.env.VITE_CHURCH_CITY}`}
          </Link>

          {/* Right Side Links */}
          <Box sx={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
            {isSmallScreen ? (
              <Drawer
                anchor="left"
                open={drawerOpen}
                onClose={toggleDrawer(false)}
              >
                <Box
                  sx={{ width: '100%' }}
                  role="presentation"
                  onClick={toggleDrawer(false)}
                  onKeyDown={toggleDrawer(false)}
                >
                  <List>
                    {isLoggedIn ? (
                      <>
                        <ListItem component="a" onClick={() => navigate('/dashboard')}>
                          <ListItemText primary={language=='en-US' ? 'Dashboard' : language=='fr-FR' ? 'Tableau De Bord' : language=='es-MX' ? 'Panel' : ''} />
                        </ListItem>
                        <ListItem component="a" onClick={() => navigate('/profile')}>
                          <ListItemText primary={language=='en-US' ? 'Profile' : language=='fr-FR' ? 'Profil' : language=='es-MX' ? 'Perfil' : ''} />
                        </ListItem>
                        <ListItem component="a" onClick={() => navigate('/auth/signout')}>
                          <ListItemText primary={language=='en-US' ? 'Logout' : language=='fr-FR' ? 'Déconnexion' : language=='es-MX' ? 'Cerrar Sesión' : ''} />
                        </ListItem>
                      </>
                    ) : (
                      <>
                        <ListItem component="a" onClick={() => navigate('/auth/signin')}>
                          <ListItemText primary={language=='en-US' ? 'Sign In' : language=='fr-FR' ? 'Se connecter' : language=='es-MX' ? 'Iniciar sesión' : ''} />
                        </ListItem>
                        <ListItem component="a" onClick={() => navigate('/auth/signup')}>
                          <ListItemText primary={language=='en-US' ? 'Sign Up' : language=='fr-FR' ? `S'inscrire` : language=='es-MX' ? 'Inscribirse' : ''} />
                        </ListItem>
                      </>
                    )}
                  </List>
                </Box>
              </Drawer>
            ) : (
              <>
                {isLoggedIn ? (
                  <>
                    <Link
                      color="inherit"
                      variant="h6"
                      underline="none"
                      sx={rightLink}
                      href="/dashboard"
                    >
                      {language=='en-US' ? 'Dashboard' : language=='fr-FR' ? 'Tableau de bord' : language=='es-MX' ? 'panel' : ''}
                    </Link>
                    <Link
                      variant="h6"
                      underline="none"
                      sx={{ ...rightLink, color: 'inherit' }}
                      href="/profile"
                    >
                      {language=='en-US' ? 'Profile' : language=='fr-FR' ? 'Profil' : language=='es-MX' ? 'Perfil' : ''}
                    </Link>
                    <Link
                      variant="h6"
                      underline="none"
                      sx={{ ...rightLink, color: 'secondary.main' }}
                      href="/auth/signout"
                    >
                    {language=='en-US' ? 'Logout' : language=='fr-FR' ? 'Déconnexion' : language=='es-MX' ? 'Cerrar sesión' : ''}
                    </Link>
                  </>
                ) : (
                  <>
                    <Link
                      color="inherit"
                      variant="h6"
                      underline="none"
                      sx={rightLink}
                      href="/auth/signin"
                    >
                      {language=='en-US' ? 'Sign In' : language=='fr-FR' ? 'Se connecter' : language=='es-MX' ? 'Iniciar sesión' : ''}
                    </Link>
                    <Link
                      variant="h6"
                      underline="none"
                      sx={{ ...rightLink, color: 'secondary.main' }}
                      href="/auth/signup"
                    >
                      {language=='en-US' ? 'Sign Up' : language=='fr-FR' ? `S'inscrire` : language=='es-MX' ? 'Inscribirse' : ''}
                    </Link>
                  </>
                )}
              </>
            )}
          </Box>
        </Toolbar>
      </AppBar>
      <Toolbar />
    </div>
  );
}

export default AppAppBar;
