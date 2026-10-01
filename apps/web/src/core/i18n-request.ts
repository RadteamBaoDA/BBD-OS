import { getRequestConfig } from 'next-intl/server';
import { messages } from './messages';

export default getRequestConfig(async () => ({
  locale: 'en-US',
  messages: messages['en-us'],
}));
