import axios from 'axios';

export const apiErrorMessage = (err: unknown): string =>
  axios.isAxiosError(err) ? String(err.response?.data?.detail ?? err.message) : 'Something went wrong';
