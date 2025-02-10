import React, { useEffect, useState } from 'react';
import AppAppBar from '../views/AppAppBar';
import AppFooter from '../views/AppFooter';
import withRoot from '../withRoot';
import Box from '@mui/material/Box';
import CheckIcon from '@mui/icons-material/Check';
import Typography from '../components/Typography';
import Button from '../components/Button';
import { SERVER } from '../../App';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store';
import AppForm from '../views/AppForm';
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Slide,
  SlideProps,
  TextField
} from '@mui/material';
import { Form, Field } from 'react-final-form';
import { email as emailValidator } from '../form/validation';
import FormFeedback from '../form/FormFeedback.tsx';
import { setLogin } from '../ducks/userSlice.ts';

// 1. Update the type to include firstName and lastName:
type UserAttribute = 'firstName' | 'lastName' | 'email' | 'password';

// 2. Update the mapping so that the update function sends the correct attribute keys:
const ATTRIBUTE_MAP: Record<UserAttribute, string> = {
  firstName: 'custom:firstName',
  lastName: 'custom:lastName',
  email: 'email',
  password: 'password',
};

function Profile() {
  const dispatch = useDispatch()
  const userEmail = useSelector((state: RootState) => state.userAuthAndInfo.user?.email);
  const [userAttributes, setUserAttributes] = useState<{ [key: string]: string } | null>(null);
  const [userEmailVerified, setUserEmailVerified] = useState(true)
  const [loading, setLoading] = useState(true);
  const [submitError, setSubmitError] = useState('');
  const [success, setSuccess] = useState('');
  const currentUser = useSelector((state: RootState) => state.userAuthAndInfo.user);

  // State to control the modal dialog and initial form values
  const [dialogOpen, setDialogOpen] = useState(false);
  const [updateType, setUpdateType] = useState<'name' | 'email' | 'password' | null>(null);
  const [initialFormData, setInitialFormData] = useState<{ [key: string]: string }>({});

  // Fetch user attributes from the server
  const fetchUserAttributes = async (email: string) => {
    try {
      const response = await fetch(`${SERVER}/user?email=${encodeURIComponent(email)}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw {
          message: errorData.message
        };
      }
      const data = await response.json();
      return data.user_attributes;
    } catch (error: any) {
      const message = error.message || 'An unexpected error occurred. Please try again later.';
      setSubmitError(message);
    }
  };

  const loginUser = async (email: string, password: string, user_name: string) => {
    try {
      const response = await fetch(`${SERVER}/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw {
          message: errorData.message
        };
      }

      const data = await response.json();

      const userData = {
        user_name: user_name,
        email: email,
      };

      const tokenData = {
        id_token: data.id_token,
        access_token: data.access_token,
        refresh_token: data.refresh_token,
      };

      localStorage.setItem('user', JSON.stringify(userData));
      localStorage.setItem('userToken', JSON.stringify(tokenData));

      dispatch(
        setLogin({
          user: userData,
          token: tokenData,
        })
      );

      return data.access_token;
    } catch (error: any) {
      const message = error.message || 'An unexpected error occurred. Please try again later.';
      setSubmitError(message);
    }
  };

  // Update user attribute on the server
  const updateUserAttribute = async (
    attributeName: string,
    attributeValue: string
  ) => {
    const cognitoAttribute = ATTRIBUTE_MAP[attributeName as UserAttribute];
    if (!cognitoAttribute) {
      console.error(`Invalid attribute name: ${attributeName}`);
      return;
    }
    setSubmitError('');
    setSuccess('');
    try {
      const response = await fetch(`${SERVER}/user`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: userEmail,
          attribute_updates: { [cognitoAttribute]: attributeValue },
        }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw {
          message: errorData.message
        };
      }
      const data = await response.json();
      setSuccess(data.message);
    } catch (err: any) {
      const message = err.message || 'An unexpected error occurred. Please try again later.';
      setSubmitError(message);
    }
  };

  useEffect(() => {
    if (userEmail) {
      fetchUserAttributes(userEmail)
        .then((attributes) => {
          if (attributes) {
            setUserAttributes(attributes);
            // Check if email_verified attribute exists and if it equals "true"
            const verified =
              attributes.email_verified &&
              attributes.email_verified.toLowerCase() === 'true';
            setUserEmailVerified(verified);
          }
          setLoading(false);
        })
        .catch((err) => setSubmitError(err.message));
    }
  }, [userEmail]);

  // Modal open handlers – set updateType and initial values
  const openNameModal = () => {
    setUpdateType('name');
    // Use the correct keys from the fetched attributes:
    setInitialFormData({
      firstName: userAttributes?.["custom:firstName"] || '',
      lastName: userAttributes?.["custom:lastName"] || '',
    });
    setDialogOpen(true);
  };

  const openEmailModal = () => {
    setUpdateType('email');
    setInitialFormData({ email: userAttributes?.email || '' });
    setDialogOpen(true);
  };

  const openPasswordModal = () => {
    setUpdateType('password');
    setInitialFormData({ password: '', confirmPassword: '' });
    setDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
    setUpdateType(null);
  };

  // Validate only the fields relevant to the current updateType
  const validate = (values: { [index: string]: string }) => {
    const errors: { [key: string]: string } = {};
    if (updateType === 'email') {
      if (!values.email) {
        errors.email = 'Email is required';
      } else {
        const emailError = emailValidator(values.email);
        if (emailError) {
          errors.email = emailError;
        }
      }
      if (!values.currentPassword) {
        errors.currentPassword = 'Current password is required';
      }
    } else if (updateType === 'password') {
      if (!values.password) {
        errors.password = 'Password is required';
      }
      if (!values.confirmPassword) {
        errors.confirmPassword = 'Confirm Password is required';
      }
      if (values.password && values.confirmPassword && values.password !== values.confirmPassword) {
        errors.confirmPassword = 'Passwords do not match';
      }
    } else if (updateType === 'name') {
      if (!values.firstName) {
        errors.firstName = 'First Name is required';
      }
      if (!values.lastName) {
        errors.lastName = 'Last Name is required';
      }
    }
    return errors;
  };  

  // Handle form submission from React Final Form
  const onSubmit = async (values: { [key: string]: string }) => {
    setSubmitError('');
    try {
      if (updateType === 'name') {
        await updateUserAttribute('firstName', values.firstName);
        await updateUserAttribute('lastName', values.lastName);
      } else if (updateType === 'email') {
        await updateUserAttribute('email', values.email);
        await loginUser(values.email, values.currentPassword, currentUser?.user_name || '');
      } else if (updateType === 'password') {
        await updateUserAttribute('password', values.password);
      }
      setDialogOpen(false);
      setUpdateType(null);
      if (userEmail) {
        const attrs = await fetchUserAttributes(userEmail);
        setUserAttributes(attrs);
      }
    } catch (err) {
    }
  };

  // Create a Transition component using Slide
  const Transition = React.forwardRef(function Transition(
    props: SlideProps,
    ref: React.Ref<unknown>
  ) {
    return <Slide direction="up" ref={ref} {...props} />;
  });

  if (loading) {
    return <Typography>Loading...</Typography>;
  }

  return (
    <React.Fragment>
      <AppAppBar />
      <AppForm>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            paddingX: '2rem',
          }}
        >
          <Typography
            variant="h4"
            marked="center"
            align="center"
            sx={{ marginBottom: '40px' }}
          >
            Profile Info
          </Typography>
          {/* Name Row */}
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '20px',
            }}
          >
            <Typography>
              {userAttributes?.["custom:firstName"]} {userAttributes?.["custom:lastName"]}
            </Typography>
            <Button onClick={openNameModal}>Change Name</Button>
          </Box>
          {/* Email Row */}
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '20px',
            }}
          >
            <Typography sx={{display: 'flex'}}>
              {userAttributes?.email}
              {userEmailVerified ? (
                <Typography>verify</Typography>
              ) : (
                <Box marginLeft={'0.5rem'}>
                  <CheckIcon />
                </Box>
              )}
              </Typography>
            <Button onClick={openEmailModal}>Change Email</Button>
          </Box>
          {/* Password Row */}
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '20px',
            }}
          >
            <Typography>********</Typography>
            <Button onClick={openPasswordModal}>Change Password</Button>
          </Box>
        </Box>
        <Box justifySelf={'center'} mb={'2rem'}>
        {submitError && (
            <Typography color="error" variant="body2">
              {submitError}
            </Typography>
          )}
          {success && (
          <FormFeedback success sx={{ mb: '2rem', mt: 2, px:'2rem', py: '0.7rem', textAlign: 'center', width: '100%', justifySelf: 'center', borderRadius: 2 }}>
            <Typography variant="h6" color="#28282a">
            Profile Updated Successfully!
            </Typography>
        </FormFeedback>
          )}
        </Box>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifySelf: 'center',
            marginTop: '20px',
            paddingX: '2rem',
            paddingY: '0.7rem',
            borderRadius: '10px',
            cursor: 'pointer'
          }}
        >
          <Typography color="white">
          <a 
            href="https://www.paypal.com/myaccount/autopay/" 
            target="_blank" 
            rel="noopener noreferrer" 
            style={{ color: '#28282a', textDecoration: '' }}
          >
              Cancel Paypal Subscription
            </a>
          </Typography>
        </Box>
      </AppForm>
      <AppFooter />

      {/* Modal Dialog for Updating Attributes */}
      <Dialog open={dialogOpen} onClose={handleCloseDialog} fullWidth maxWidth="sm"
        PaperProps={{
          sx: {
            py: { xs: 3, md: 6 }, px: { xs: 3, md: 6 },
            backgroundColor: '#fff5f8'
          }
        }}

      >
        <DialogTitle>
          {updateType === 'name' && 'Change Name'}
          {updateType === 'email' && 'Change Email'}
          {updateType === 'password' && 'Change Password'}
        </DialogTitle>
        <Form
          onSubmit={onSubmit}
          validate={validate}
          initialValues={initialFormData}
          render={({ handleSubmit, submitting, pristine }) => (
            <form onSubmit={handleSubmit}>
              <DialogContent>
                {updateType === 'name' && (
                  <>
                    <Field name="firstName">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="First Name"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                    <Field name="lastName">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="Last Name"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                  </>
                )}
                {updateType === 'email' && (
                  <>
                    <Field name="email">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="New Email"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                    <Field name="currentPassword">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="Current Password"
                          type="password"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                  </>
                )}
                {updateType === 'password' && (
                  <>
                    <Field name="password">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="New Password"
                          type="password"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                    <Field name="confirmPassword">
                      {({ input, meta }) => (
                        <TextField
                          {...input}
                          margin="dense"
                          label="Confirm Password"
                          type="password"
                          fullWidth
                          error={meta.touched && Boolean(meta.error)}
                          helperText={meta.touched && meta.error}
                        />
                      )}
                    </Field>
                  </>
                )}
              </DialogContent>
              <DialogActions>
                <Button onClick={handleCloseDialog}>Cancel</Button>
                <Button type="submit" color="primary" disabled={submitting || pristine}>
                  Submit
                </Button>
              </DialogActions>
            </form>
          )}
        />
      </Dialog>
    </React.Fragment>
  );
}

export default withRoot(Profile);